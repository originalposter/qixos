# TODO: Make tests
# TODO: Better logging
#  - Not to stdout
#  - Use logging lib
#  - Swallow stdout in admin
# TODO: Consider moving protocol reading and writing code to protocol module
from pathlib import Path
import logging
import logging.handlers
import sys
import tarfile
import json
import subprocess
import shutil
import os
import signal
from string import Template
from .protocol import ProtocolJson, Flake, BreakingProtocolError, UnknownError, VersionNotSupportedError, UntarError, MissingAttributeError, NixosRebuildError, MakeGitError, OomKillerError, AppVmBuildError, SWITCH_LOG_PATH, SWITCH_LOG_TAG

# Implements the qixos.Switch protocol between the qixos-admin VM's qixos-rebuild script
# and the template VM running this script.
# This script is responsible for building the templates nixos derivation and then, one at a
# time, each associated AppVM's derivation.
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

TEMPLATE_FLAKE_DIR = "/var/qixos/template-flake"
TEMPLATE_FLAKE_PATH = f"{TEMPLATE_FLAKE_DIR}/flake.nix"
# Outside TEMPLATE_FLAKE_DIR, which nix reads as a path flake and so copies whole into the
# store on every switch.
LOCAL_REPOS_DIR = Path("/var/qixos/local-repos")

INPUT_TEMPLATE_FLAKE_NAME = "template"

# Each AppVM gets a generated flake of its own, in APPVM_FLAKES_DIR/<name>. One flake for
# the whole cluster would be locked as a whole, which fetches every AppVM's inputs before
# the template has switched and lets one that cannot be fetched fail them all.
APPVM_FLAKES_DIR = Path("/var/qixos/appvm-flakes")
# ACTIVATION_DIR/<name>/nixos is the closure an AppVM switches to at boot. On the root
# volume, since that is what an AppVM takes from its template. Must match activationDir in
# qixos-nix-libs/make-nube-system.nix.
ACTIVATION_DIR = Path("/var/qixos/activation")

# Where `nixos-rebuild boot` leaves the system it built.
SYSTEM_PROFILE = "/nix/var/nix/profiles/system"

QUBES_HTTP_PROXY_URL = "http://127.0.0.1:8082"

# Inputs that every AppVM is forced to share with its template. An AppVM's closure is
# evaluated and built by its template and read out of the template's /nix/store, so the two
# differing on either of these is incoherent. Different clusters may still pin different
# versions - the template flake is where that choice lives.
# These names are a convention. Nix only warns if an AppVM names its inputs something else,
# in which case that AppVM keeps its own pin.
INPUT_FOLLOWED_FROM_TEMPLATE = ["nixpkgs", "qixCore"]


_log = logging.getLogger("qixos.switch")


def setup_logging():
    """Send this script's output to the journal and to a file.

    Not to stderr where it is unreadable since it is sent to the admin over qrexec
    and the admin drops it.
    """
    os.makedirs(os.path.dirname(SWITCH_LOG_PATH), exist_ok=True)

    journal = logging.handlers.SysLogHandler("/dev/log")
    journal.setFormatter(logging.Formatter(f"{SWITCH_LOG_TAG}: %(message)s"))

    # Capped
    disk = logging.handlers.RotatingFileHandler(SWITCH_LOG_PATH, maxBytes=1 << 20, backupCount=3)
    disk.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

    _log.setLevel(logging.INFO)
    _log.addHandler(journal)
    _log.addHandler(disk)


def log(m):
    _log.info("%s", m)


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
    shutil.rmtree(LOCAL_REPOS_DIR, ignore_errors=True)
    os.makedirs(LOCAL_REPOS_DIR, exist_ok=True)

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
            tar_dir_absolute = LOCAL_REPOS_DIR / tar_dir
            reader = TarReader(sys.stdin.buffer, blob_length)
            with tarfile.open(fileobj=reader, mode='r|') as tf:
                # filter="data" sets ownership to the caller, so files are owned by root.
                # It also does not accept symlinks which means the tar dir can't contain those.
                tf.extractall(path=tar_dir_absolute, filter="data")
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


def locked_template_input() -> str:
    """The template input as the generated template flake locked it, as a nix attrset.

    An AppVM's flake names the template by this rather than by its url, so the AppVM is
    built against the very revision the template was, whatever that url resolves to by
    the time the AppVM's flake is locked.
    """
    with open(f"{TEMPLATE_FLAKE_DIR}/flake.lock") as f:
        nodes = json.load(f)["nodes"]
    locked = nodes[nodes["root"]["inputs"][INPUT_TEMPLATE_FLAKE_NAME]]["locked"]
    # A lock holds strings, integers and booleans, which JSON and nix write the same way.
    return "{ " + " ".join(f"{key} = {json.dumps(value)};" for key, value in locked.items()) + " }"


def appvm_sources(protocol: ProtocolJson) -> dict[str, Flake]:
    """Each AppVM's inner config, with a local one's source rewritten to where it was untarred."""
    sources = dict(protocol.remote_appvms)
    for name, local in protocol.local_appvms.items():
        url = local_path_to_local_flake_url(local.flake.source, LOCAL_REPOS_DIR / local.dir_name)
        sources[name] = Flake(source=url, output=local.flake.output)
    return sources


def generate_appvm_flake(name: str, appvm: Flake, template_input: str, template_attribute: str):
    follows = '\n    '.join(
        f"appvm.inputs.{input_name}.follows = \"{INPUT_TEMPLATE_FLAKE_NAME}/{input_name}\";"
        for input_name in INPUT_FOLLOWED_FROM_TEMPLATE
    )

    flake = Template('''{
  # THIS FILE WAS AUTO-GENERATED BY qixos.Switch IN THE qixos-rebuild LIFECYCLE
  inputs = {
    # The template as ${TEMPLATE_FLAKE_PATH} locked it
    ${INPUT_TEMPLATE_FLAKE_NAME} = ${template_input};
    appvm.url = "${flake_url}";
    ${follows}
  };

  outputs = inputs:
    let
      template = inputs.${INPUT_TEMPLATE_FLAKE_NAME}.${template_attribute};
    in {
      nixosConfigurations."${name}" = template.lib.mkNubeSystem inputs.appvm.${output}.config;
    };
}''').substitute(
        INPUT_TEMPLATE_FLAKE_NAME=INPUT_TEMPLATE_FLAKE_NAME,
        TEMPLATE_FLAKE_PATH=TEMPLATE_FLAKE_PATH,
        template_input=template_input,
        flake_url=appvm.source,
        follows=follows,
        template_attribute=template_attribute,
        name=name,
        output=appvm.output,
    )

    os.makedirs(APPVM_FLAKES_DIR / name, exist_ok=True)
    with open(APPVM_FLAKES_DIR / name / "flake.nix", 'w') as f:
        f.write(flake)


def generate_template_flake(protocol: ProtocolJson):
    template_attribute = protocol.template_flake.output
    if protocol.template_dirname is not None:
        template_flake_url = local_path_to_local_flake_url(protocol.template_flake.source, LOCAL_REPOS_DIR / protocol.template_dirname)
    else:
        template_flake_url = protocol.template_flake.source

    # Currently we fetch the mkNubeSystem function from the template input
    # because this allows us to not have to hardcode our own lib input or a separate input.
    # The template will have this function included in it by the wrapper function producing the
    # template output
    flake = Template('''{
  # THIS FILE WAS AUTO-GENERATED BY qixos.Switch IN THE qixos-rebuild LIFECYCLE
  # The AppVMs of this template each have a flake of their own in ${APPVM_FLAKES_DIR}
  inputs = {
    ${INPUT_TEMPLATE_FLAKE_NAME}.url = "${template_flake_url}";
  };

  # The template ships the mkNubeSystem function from the qixos nix library
  outputs = inputs:
    let
      template = inputs.${INPUT_TEMPLATE_FLAKE_NAME}.${template_attribute};
    in {
      nixosConfigurations.template = template.lib.mkNubeSystem template.config;
    };
}''').substitute(
        APPVM_FLAKES_DIR=APPVM_FLAKES_DIR,
        template_flake_url=template_flake_url,
        INPUT_TEMPLATE_FLAKE_NAME=INPUT_TEMPLATE_FLAKE_NAME,
        template_attribute=template_attribute,
    )

    os.makedirs(TEMPLATE_FLAKE_DIR, exist_ok=True)
    with open(TEMPLATE_FLAKE_PATH, 'w') as f:
        f.write(flake)


def prefer_as_oom_victim():
    """Make this process the kernel's first choice if memory runs out.

    Run in the child between fork and exec. A nix build is what consumes the memory here
    and it is the safe thing to lose: builds are atomic, so a killed one leaves nothing
    behind. What must survive is this switch, which is the only thing that can report why
    the build failed. Raising a score needs no privilege, unlike lowering one, and biasing
    the child up beats biasing the parent down because the setting is inherited.

    Only chooses a victim if the kernel is already out of memory. It does not make one
    more likely.
    """
    with open("/proc/self/oom_score_adj", "w") as adj:
        adj.write("500")


def oom_kills():
    """How many processes the kernel has OOM-killed since boot, or None if it will not say.

    The counter is system-wide. On a template mid-switch that is close enough: anything
    the kernel killed for memory during a build is the same diagnosis and the same fix.
    """
    try:
        with open("/proc/vmstat") as vmstat:
            for line in vmstat:
                name, _, count = line.partition(" ")
                if name == "oom_kill":
                    return int(count)
    except (OSError, ValueError):
        pass
    return None


def lock_flake(flake_dir, update_lockfile: bool):
    if update_lockfile:
        lock_args = ["nix", "flake", "update", "--allow-dirty-locks", "--refresh", "--flake", str(flake_dir)]
    else:
        lock_args = ["nix", "flake", "lock", "--allow-dirty-locks", str(flake_dir)]

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


def run_build(args, what: str, env):
    """Run a nix build, telling one the kernel killed for memory from one that failed."""
    kills_before = oom_kills()
    try:
        subprocess.run(args, check=True, capture_output=True, preexec_fn=prefer_as_oom_victim, env=env)
    except subprocess.CalledProcessError as err:
        # The kernel usually takes the nix build rather than the command we ran, which
        # then exits with an ordinary non-zero status and says nothing about memory. So
        # ask the kernel what it did instead of reading the status.
        kills_after = oom_kills()
        killed = (
            kills_before is not None
            and kills_after is not None
            and kills_after > kills_before
        )
        if err.returncode == -signal.SIGKILL or killed:
            raise OomKillerError(
                f"the kernel killed a process for memory while {what} ran. Give the "
                f"template more memory and switch again: {err.stderr.decode()}"
            )
        raise NixosRebuildError(f"{what} failed: {err.stderr.decode()}")


def activate_template():
    """Bring the running template up to the configuration it was just rebuilt to.

    So that the AppVM builds run with whatever the new configuration provides, split-ssh
    for fetching private inputs being the example. A refusal is not an error: switch
    inhibitors turn down a live activation that the next boot accepts, the builds do not
    depend on it, and an AppVM that did need it fails its own build and nothing else.
    """
    result = subprocess.run([f"{SYSTEM_PROFILE}/bin/switch-to-configuration", "test"], capture_output=True)
    if result.returncode != 0:
        log(f"could not activate the new template configuration, building the AppVMs without it: {result.stderr.decode()}")


def forget_removed_appvms(appvm_names):
    """Drop what was kept for AppVMs that have left the cluster.

    The out-link is the only thing holding such an AppVM's closure in the store.
    """
    for kept in (APPVM_FLAKES_DIR, ACTIVATION_DIR):
        if not kept.is_dir():
            continue
        for entry in kept.iterdir():
            if entry.name not in appvm_names:
                shutil.rmtree(entry)


def build_and_switch(protocol: ProtocolJson):
    build_env = {"https_proxy": QUBES_HTTP_PROXY_URL, "all_proxy": QUBES_HTTP_PROXY_URL, **os.environ} if not protocol.standalone else None

    lock_flake(TEMPLATE_FLAKE_DIR, protocol.update_lockfile)
    log(f"switching to new flake configuration at {TEMPLATE_FLAKE_DIR}/flake.nix\nThis may take a while...")
    run_build(
        # We prefer boot over switch here because sometimes we hit 'SwitchInhibitors' that disallow switching.
        # booting is safer and we will reboot the template (and standalone for now) after this anyway.
        ["nixos-rebuild", "boot", "--flake", f"{TEMPLATE_FLAKE_DIR}#template"],
        "nixos-rebuild",
        build_env,
    )

    appvms = appvm_sources(protocol)
    forget_removed_appvms(appvms)
    if not appvms:
        return

    activate_template()
    template_input = locked_template_input()

    # One nix at a time. Each evaluates a whole NixOS system, and several at once is the
    # memory peak that building them apart is meant to avoid.
    failed = []
    out_of_memory = False
    for name in sorted(appvms):
        flake_dir = APPVM_FLAKES_DIR / name
        out_link = ACTIVATION_DIR / name / "nixos"
        log(f"building AppVM [{name}] from {flake_dir}/flake.nix")
        try:
            generate_appvm_flake(name, appvms[name], template_input, protocol.template_flake.output)
            lock_flake(flake_dir, protocol.update_lockfile)
            os.makedirs(out_link.parent, exist_ok=True)
            # A failed build leaves the previous out-link alone, so the AppVM keeps
            # booting the last closure that did build.
            run_build(
                ["nix", "build", f'{flake_dir}#nixosConfigurations."{name}".config.system.build.toplevel', "--out-link", str(out_link)],
                f"the build of AppVM [{name}]",
                build_env,
            )
        except OomKillerError as e:
            log(e)
            failed.append(name)
            out_of_memory = True
        except (NixosRebuildError, OSError) as e:
            log(e)
            failed.append(name)

    # 17 rather than 18 although the template did switch: the admin gets one status, and
    # that the template needs more memory is the half someone can act on. The admin
    # cannot tell this from a kill during the template's own build, so it stops there.
    if out_of_memory:
        raise OomKillerError(f"the template switched but ran out of memory building AppVMs: {', '.join(failed)}")
    if failed:
        raise AppVmBuildError(f"the template switched but these AppVMs failed to build: {', '.join(failed)}")


def main():
    setup_logging()
    log("qixos.Switch starting...")
    try:
        protocol_result = read_protocol()
        generate_template_flake(protocol_result)
        build_and_switch(protocol_result)
        log(f"successfully switched to: {TEMPLATE_FLAKE_PATH}")
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
    except AppVmBuildError as e:
        log(e)
        sys.exit(e.ERROR_CODE)
    except Exception as e:
        log(f"UNKNOWN ERROR code: {e}")
        sys.exit(UnknownError.ERROR_CODE)


if __name__ == "__main__":
    main()
