from pathlib import Path
import re
import subprocess
from .errors import ConfigError, NixError
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.alias_generators import to_camel


# Values a config can give a property in place of a qube name. Both are translated at the
# write boundary rather than passed through: QUBES_DEFAULT becomes qubesadmin.DEFAULT, and
# QUBES_NONE becomes None. A qube actually named "default" or "none" is unreferenceable,
# which is the price of spelling these in the same field as the name.
QUBES_DEFAULT = "default"
QUBES_NONE = "none"


class CamelModel(BaseModel):
    # extra="forbid" so an unknown key is an error rather than a silent drop: a misspelled
    # property, or one this qixos does not know yet, otherwise leaves a config that
    # quietly does less than it says. Both spellings of a field stay valid, since
    # populate_by_name makes them names rather than extras.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class VmProperties(CamelModel):
    # Order is the order `apply` reconciles them in. Only netvm cares: it is skipped by
    # the generic loop and handled separately, because setting it can require starting
    # the qube it names.
    label: str
    memory: int | None = None
    maxmem: int | None = None
    vcpus: int | None = None
    autostart: bool | None = None
    include_in_backups: bool | None = None
    qrexec_timeout: int | None = None
    shutdown_timeout: int | None = None
    provides_network: bool | None = None
    template_for_dispvms: bool | None = None
    # After template_for_dispvms: qubes refuses a defaultDispvm whose target does not
    # carry that flag, and the target may be getting it in this same reconcile.
    default_dispvm: str | None = None
    # Three states, like every other property here: unset means qixos does not manage it,
    # QUBES_DEFAULT means the qubes default, QUBES_NONE means no network at all.
    netvm: str | None = None

    @field_validator("netvm", mode="before")
    @classmethod
    def empty_string_means_none(cls, v):
        return QUBES_NONE if v == "" else v

    @model_validator(mode="after")
    def memory_fits_under_maxmem(self) -> "VmProperties":
        # qubes takes either write in any order and only bites at VM start, so the config
        # is the last place this can be caught with a sentence rather than with a qube
        # that will not boot. maxmem 0 disables ballooning and is not a ceiling.
        if self.memory is not None and self.maxmem not in (None, 0) and self.memory > self.maxmem:
            raise ConfigError(
                f"memory {self.memory} is above maxmem {self.maxmem}, so this qube "
                "could not balloon down to its own starting size"
            )
        return self


_SIZE_UNITS = {
    "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
    "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
}

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*$")


def _parse_size(v: object) -> int | None:
    """Bytes from a size like "20 GiB".

    A number is refused rather than read as bytes, whether the config writes it as one or
    quotes it. Nobody sizing a disk means bytes, so the one config that would be taken
    literally is a typo for something a billion times smaller than it looks.

    None is the volume being unmanaged, which is not this function's business.
    """
    if v is None:
        return None
    match = _SIZE.match(v) if isinstance(v, str) else None
    if match is None or match.group(2).lower() not in _SIZE_UNITS:
        raise ConfigError(
            f"could not read {v!r} as a size. Write a number and a unit, like "
            f"'20 GiB', using one of: {', '.join(sorted(_SIZE_UNITS))}"
        )
    return int(float(match.group(1)) * _SIZE_UNITS[match.group(2).lower()])


class Volumes(CamelModel):
    """Sizes qixos keeps a VM's volumes at or above.

    A volume left unset is not managed. Both are floors rather than exact sizes: qubes
    rounds an allocation up to the pool's own granularity, and only growth is supported
    anyway.
    """
    # An AppVM's root is a snapshot of its template's, which qubes will not resize, so
    # AppVMConfig refuses this below and a cluster's root size is the template's.
    root: int | None = None
    private: int | None = None

    _to_bytes = field_validator("root", "private", mode="before")(_parse_size)


class LocalFlake(CamelModel):
    path: Path
    output: str
    copy_dir: Path | None = None


class RemoteFlake(CamelModel):
    url: str
    output: str


# We prefer inheritance rather than composition because
# it cleanly lets us deserialize in a flat manner.
class VmConfigMixin(CamelModel):
    delete_on_removal: bool = False
    rename_from: str | None = None
    properties: VmProperties
    volumes: Volumes = Volumes()
    remote_flake: RemoteFlake | None = None
    local_flake: LocalFlake | None = None

    @model_validator(mode="after")
    def exactly_one_flake(self) -> "VmConfigMixin":
        if self.remote_flake is None and self.local_flake is None:
            raise ConfigError("exactly one of remoteFlake or localFlake must be set")
        if self.remote_flake is not None and self.local_flake is not None:
            raise ConfigError("only one of remoteFlake or localFlake can be set")
        return self


class AppVMConfig(VmConfigMixin):
    @model_validator(mode="after")
    def no_root_volume(self) -> "AppVMConfig":
        # Refused rather than ignored: qubes rejects the resize, and a line that reads
        # like it sets the root size while doing nothing is worse than an error.
        if self.volumes.root is not None:
            raise ConfigError(
                "an AppVM's root volume is a snapshot of its template's and cannot be "
                "resized. Put the root size on the cluster's template instead."
            )
        return self


class TemplateVMConfig(VmConfigMixin):
    pass


class StandaloneVMConfig(VmConfigMixin):
    pass


class NubeClusterConfig(CamelModel):
    app_vms: dict[str, AppVMConfig]
    template: TemplateVMConfig


class QixosConfig(CamelModel):
    nube_clusters: dict[str, NubeClusterConfig] = {}
    standalone_nubes: dict[str, StandaloneVMConfig] = {}
    management_tag: str
    base_template: str


def eval_config(flake: str) -> QixosConfig:
    # Split the flake string on # and put in the qixosConfigurations.{output}
    # unless it starts with qixosConfiguration.
    try:
        url, output = flake.rsplit('#', 1)
        if not output.startswith("qixosConfigurations"):
            output = "qixosConfigurations." + output
    except ValueError as e:
        raise NixError("flake url must contain a #") from e

    try:
        result = subprocess.run(
            ["nix", "eval", f"{url}#{output}", "--refresh", "--json"],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        raise NixError(f"could not evaluate flake: {e.stderr}") from e

    qixos_config = QixosConfig.model_validate_json(result.stdout)
    return qixos_config
