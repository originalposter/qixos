from pathlib import Path
import subprocess
from .errors import ConfigError, NixError
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class VmProperties(CamelModel):
    label: str
    provides_network: bool | None = None
    template_for_dispvms: bool | None = None
    netvm: str | None = "default"

    @field_validator("netvm", mode="before")
    @classmethod
    def none_string_to_none(cls, v):
        if v == "none" or v == "":
            return None
        return v


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
