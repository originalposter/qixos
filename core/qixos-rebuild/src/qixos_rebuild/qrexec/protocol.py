from pydantic import BaseModel

# Where qixos.Switch logs on the template. Shared because the admin cannot read that log
# but has to be able to say where it is.
SWITCH_LOG_PATH = "/var/qixos/switch.log"
SWITCH_LOG_TAG = "qixos.Switch"

# If a FlakePath is local it MUST be relative to the tarred directory root
type FlakeSource = str
type VmName = str
type DirName = str
type Output = str


class Flake(BaseModel):
    source: FlakeSource
    output: Output


class FlakeAndDir(BaseModel):
    dir_name: DirName
    flake: Flake


class ProtocolJson(BaseModel):
    # None if not local
    template_dirname: DirName | None
    template_flake: Flake
    remote_appvms: dict[VmName, Flake]
    local_appvms: dict[VmName, FlakeAndDir]
    # List of dirnames in the order they are sent as tars
    tar_dirs: list[DirName]
    update_lockfile: bool
    standalone: bool = False


class BreakingProtocolError(Exception):
    ERROR_CODE = 1000


class VersionNotSupportedError(Exception):
    ERROR_CODE = 1001


class UntarError(Exception):
    ERROR_CODE = 1002


class MissingAttributeError(Exception):
    ERROR_CODE = 1003


class NixosRebuildError(Exception):
    ERROR_CODE = 1004


class MakeGitError(Exception):
    ERROR_CODE = 1005


class OomKillerError(Exception):
    ERROR_CODE = 1006
