from pathlib import Path
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
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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
    pass


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
