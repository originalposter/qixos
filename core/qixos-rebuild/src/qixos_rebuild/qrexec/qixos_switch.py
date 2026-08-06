# TODO: Make tests
# TODO: Better logging
#  - Not to stdout
#  - Use logging lib
#  - Swallow stdout in admin
# TODO: Consider moving protocol reading and writing code to protocol module
from pathlib import Path
import sys
import tarfile
import subprocess
import shutil
import os
import signal
from string import Template
from .protocol import ProtocolJson, BreakingProtocolError, VersionNotSupportedError, UntarError, MissingAttributeError, NixosRebuildError, MakeGitError, OomKillerError

# Implements the qixos.Switch protocol between the qixos-admin VM's qixos-rebuild script
# and the template VM running this script.
# This script is responsible for building the templates nixos derivation and all the associated
# AppVM's derivations.
# The protocol is entirely uni-directional from the qixos-admin to the template.
# The protocol contains the following steps:
# 1. Send a line containing the version of the protocol in the format: v<integer>, e.g v0
# For the v0 of this protocol:
# 2. Send a line containing an ascii encoded integer, J, of the number of bytes in the following JSON blob
# 3. Send a JSON blob containing the template flake url and appvm flake urls
# Any local flake url MUST be relative to the tarred directory
# 4. For each dirname in the JSON blob do the following:
# 5. Send a line containing an ascii encoded integer, B, of the number of bytes
# in the following tar stream
# 6. Send a stream of B bytes of a tar stream
# 7. If there are more dirnames go to 4
#
# This script should untar the tar stream into a directory which local paths are relative to

CURRENT_FLAKE_DIR = "/var/qixos/current-flake"
CURRENT_FLAKE_PATH = f"{CURRENT_FLAKE_DIR}/flake.nix"
CURRENT_FLAKE_COPIED_DIR = Path(f"{CURRENT_FLAKE_DIR}/local-repos")

INPUT_TEMPLATE_FLAKE_NAME = "template"

# Inputs that every AppVM is forced to share with its template. An AppVM's closure is
# evaluated and built by its template and read out of the template's /nix/store, so the two
# differing on either of these is incoherent. Different clusters may still pin different
# versions - the template flake is where that choice lives.
# These names are a convention. Nix only warns if an AppVM names its inputs something else,
# in which case that AppVM keeps its own pin.
INPUT_FOLLOWED_FROM_TEMPLATE = ["nixpkgs", "qixCore"]


def log(m):
    print(m, file=sys.stderr)


class TarReader:
    def __init__(self, stream, n):
        self.stream = stream
        self.remaining = n

    def read(self, size=-1):
        if self.remaining == 0:
            return b''
        if size == -1:
            size = self.remaining
        size = min(size, self.remaining)
        data = self.stream.read(size)
        self.remaining -= len(data)
        return data


def make_git(repo_root: Path):
    try:
        subprocess.run(["git", "init", repo_root], check=True)
        subprocess.run(["git", "-C", repo_root, "add", "."], check=True)
    except subprocess.CalledProcessError as err:
        raise MakeGitError(f"failed to make a directory a git repo: {err}")


def reset_ownership(member, _):
    member.uid = 0
    member.gid = 0
    member.uname = "root"
    member.gname = "root"
    return member


def read_protocol():
    # GET VERSION
    try:
        vstring = sys.stdin.buffer.readline().decode().strip()
        if not vstring.startswith('v'):
            raise BreakingProtocolError(f"version string must start with 'v' but got {vstring}")

        version = int(vstring[1:])
    except ValueError as e:
        raise BreakingProtocolError(f"version not convertable to integer: {e}")
    if version != 0:
        raise VersionNotSupportedError(f"version {version} not supported")

    # GET THE JSON BLOB BYTE LENGTH
    blob_length_string = sys.stdin.buffer.readline().decode().strip()
    try:
        blob_length = int(blob_length_string)
    except ValueError as e:
        raise BreakingProtocolError(f"JSON blob bytes not convertable to integer: {e}")

    # GET THE JSON BLOB
    json_blob_raw = sys.stdin.buffer.read(blob_length).decode("utf-8")
    json_blob: ProtocolJson = ProtocolJson.model_validate_json(json_blob_raw)

    # Delete the old directory
    try:
        shutil.rmtree(CURRENT_FLAKE_COPIED_DIR)
    except FileNotFoundError:
        pass
    os.makedirs(CURRENT_FLAKE_COPIED_DIR, exist_ok=True)

    for tar_dir in json_blob.tar_dirs:
        # GET THE TAR STREAM LENGTH
        tar_length_string = sys.stdin.buffer.readline().decode().strip()
        log(f"tar blob byte size: {tar_length_string}")
        try:
            blob_length = int(tar_length_string)
        except ValueError as e:
            raise BreakingProtocolError(f"tar length bytes not convertable to integer: {e}")

        # GET THE TAR STREAM
        try:
            tar_dir_absolute = CURRENT_FLAKE_COPIED_DIR / tar_dir
            reader = TarReader(sys.stdin.buffer, blob_length)
            with tarfile.open(fileobj=reader, mode='r|') as tf:
                tf.extractall(path=tar_dir_absolute, filter=reset_ownership)
            # Need to make non-git dirs into git repos for nix to see them properly
            is_git = (tar_dir_absolute / ".git").exists()
            if not is_git:
                make_git(tar_dir_absolute)

        except Exception as e:
            raise UntarError(f"could not untar the stream {e}")

    return json_blob


def local_path_to_local_flake_url(local_path: str, tar_dir: Path) -> str:
    """
    Rewrite a local flake-like path to an absolute flake installable
    rooted at the extracted tarball directory.

    The input is of the form "<relative-path>", where
    <relative-path> is interpreted relative to tar_dir. The output is
    "git+file://<tar-dir>?dir=relative" which Nix recognizes as a local
    flake installable.
    """

    # Normalize: strip leading './' if present, reject absolute paths and
    # parent-directory traversal.
    if local_path.startswith("/"):
        raise ValueError(
            f"local flake path must be relative, got absolute: {local_path!r}"
        )
    if local_path.startswith("./"):
        local_path = local_path[2:]
    if ".." in local_path.split("/"):
        raise ValueError(
            f"local flake path may not contain '..': {local_path!r}"
        )

    return f"git+file://{tar_dir}?dir={local_path}"


def follows_from_template(appvm_name: str) -> list[str]:
    """Input override lines pinning an AppVM to the template's shared inputs.

    See INPUT_FOLLOWED_FROM_TEMPLATE for why these are forced.
    """
    return [
        f"{appvm_name}.inputs.{input_name}.follows = \"{INPUT_TEMPLATE_FLAKE_NAME}/{input_name}\";"
        for input_name in INPUT_FOLLOWED_FROM_TEMPLATE
    ]


def generate_flake(protocol: ProtocolJson):
    input_strings = []
    output_appvm_strings = []

    for name, local_appvm_data in protocol.local_appvms.items():
        appvm_name = f"\"appvm-{name}\""
        flake_url = local_path_to_local_flake_url(local_appvm_data.flake.source, CURRENT_FLAKE_COPIED_DIR / local_appvm_data.dir_name)
        input_strings.append(f"{appvm_name}.url = \"{flake_url}\";")
        input_strings.extend(follows_from_template(appvm_name))
        output_appvm_strings.append(f"{name} = inputs.{appvm_name}." + f"{local_appvm_data.flake.output}.config;")

    for name, flake in protocol.remote_appvms.items():
        appvm_name = f"\"appvm-{name}\""
        input_strings.append(f"{appvm_name}.url = \"{flake.source}\";")
        input_strings.extend(follows_from_template(appvm_name))
        output_appvm_strings.append(f"{name} = inputs.{appvm_name}." + f"{flake.output}.config;")

    if protocol.template_dirname is not None:
        template_attribute = protocol.template_flake.output
        template_flake_url = local_path_to_local_flake_url(protocol.template_flake.source, CURRENT_FLAKE_COPIED_DIR / protocol.template_dirname)
    else:
        template_flake_url = protocol.template_flake.source
        template_attribute = protocol.template_flake.output

    input_strings.append(f"{INPUT_TEMPLATE_FLAKE_NAME}.url = \"{template_flake_url}\";")
    template_output_string = f"inputs.{INPUT_TEMPLATE_FLAKE_NAME}." + f"{template_attribute}.config;"

    inputs = '\n    '.join(input_strings)
    output_appvms = '\n      '.join(output_appvm_strings)

    # Currently we fetch the mkNubeCluster function from the template input
    # because this allows us to not have to hardcode our own lib input or a separate input.
    # The template will have this function included in it by the wrapper function producing the
    # template output
    flake = Template('''{
  # THIS FILE WAS AUTO-GENERATED BY qixos.Switch IN THE qixos-rebuild LIFECYCLE
  inputs = {
    ${inputs}
  };

  # The template ships the mkNubeClusterWith package from the qixos nix library
  outputs = inputs: inputs.${INPUT_TEMPLATE_FLAKE_NAME}.${template_attribute}.lib.mkNubeCluster {
    template = ${template_output_string}
    apps = {
      ${output_appvms}
    };
  };
}''').substitute(
        inputs=inputs,
        output_appvms=output_appvms,
        template_output_string=template_output_string,
        INPUT_TEMPLATE_FLAKE_NAME=INPUT_TEMPLATE_FLAKE_NAME,
        template_attribute=template_attribute,
    )

    with open(CURRENT_FLAKE_PATH, 'w') as f:
        f.write(flake)


def build_and_switch(update_lockfile: bool, standalone: bool):
    QUBES_HTTP_PROXY_URL = "http://127.0.0.1:8082"

    if update_lockfile:
        lock_args = [
            "nix",
            "flake",
            "update",
            "--allow-dirty-locks",
            "--refresh",
            "--flake",
            str(CURRENT_FLAKE_DIR),
        ]
    else:
        lock_args = [
            "nix",
            "flake",
            "lock",
            "--allow-dirty-locks",
            str(CURRENT_FLAKE_DIR),
        ]

    try:
        subprocess.run(
            lock_args,
            check=True,
            capture_output=True,
            env={
                "https_proxy": QUBES_HTTP_PROXY_URL,
                "all_proxy": QUBES_HTTP_PROXY_URL,
                **os.environ
            },
        )
    except subprocess.CalledProcessError as err:
        raise NixosRebuildError(f"nix flake lock failed: {err.stderr.decode()}")

    try:
        log(f"switching to new flake configuration at {CURRENT_FLAKE_DIR}/flake.nix\nThis may take a while...")
        subprocess.run(
            # We prefer boot over switch here because sometimes we hit 'SwitchInhibitors' that disallow switching.
            # booting is safer and we will reboot the template (and standalone for now) after this anyway.
            ["nixos-rebuild", "boot", "--flake", f"{CURRENT_FLAKE_DIR}#template"],
            check=True,
            capture_output=True,
            env={"https_proxy": QUBES_HTTP_PROXY_URL, "all_proxy": QUBES_HTTP_PROXY_URL, **os.environ} if not standalone else None,

        )
    except subprocess.CalledProcessError as err:
        if err.returncode == -signal.SIGKILL:
            raise OomKillerError("SIGKILL detected when running nixos-rebuild. Likely an oom killer")
        raise NixosRebuildError(f"nixos-rebuild failed: {err.stderr.decode()}")


def main():
    log("qixos.Switch starting...")
    try:
        protocol_result = read_protocol()
        generate_flake(protocol_result)
        build_and_switch(protocol_result.update_lockfile, protocol_result.standalone)
        log(f"successfully switched to: {CURRENT_FLAKE_PATH}")
    except BreakingProtocolError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except VersionNotSupportedError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except UntarError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except MissingAttributeError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except NixosRebuildError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except MakeGitError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except OomKillerError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except Exception as e:
        UNKNOWN_ERROR_CODE = -9999
        log(f"UNKNOWN ERROR code: {e}")
        sys.exit(UNKNOWN_ERROR_CODE)


if __name__ == "__main__":
    main()
