import logging
import subprocess
import tempfile
import os
import hashlib

from qixos_rebuild.errors import LocalFlakeError, QixosSwitchError
from .config import LocalFlake, QixosConfig, NubeClusterConfig, StandaloneVMConfig
from qubesadmin.app import QubesBase
from pathlib import Path
from qixos_rebuild.qrexec.protocol import ProtocolJson, Flake, FlakeAndDir, OomKillerError

QREXEC_SERVICE = "qixos.Switch"
REMOTE_SWITCH_ARGUMENT = "REMOTE"
LOCAL_SWITCH_ARGUMENT = "LOCAL"
PROTOCOL_VERSION = "v0"


log = logging.getLogger("qixos.switch")


def _flake_argument_to_qixos_config_dir(flake_arg: str) -> Path:
    relative_path, _ = flake_arg.rsplit('#', 1)
    return Path.cwd() / relative_path


# Get the git root of a path
# We assume `git` exists here, if not it will throw an error
# We don't really care to handle this error since this is a basically
# safe assumption unless someone really knows what they are doing and removed git.
# In that case they will have to manually use copyDir if they want to use a local copy.
def _git_root(path: Path) -> Path:
    # TODO: Error in case this isn't a git repo
    return Path(subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        text=True
    ).strip())


# Accepts a local flake and the qixosConfiguration flake path.
# Returns a relative path to use for the local flake and a
# path to a dir to copy and which the flake path is relative to.
#
# There are various "modes" that this protocol follows depending on what is found in `local_flake`
# 1. If local_flake.copy_dir is set then that directory is copied to the target nube
# and local_flake.path *must* be a relative path which is relative to the root of that copy_dir directory.
# 2. If local_flake.copy_dir is None and local_flake.path is a relative path then the git root
# of the qixos config directory is taken to be copy_dir.
# 3. If local_flake.copy_dir is None and local_flake.path is absolute then the git root of that
# path is taken to be copy_dir.
#
# There are some invariants that are not allowed.
# If local_flake.copy_dir is set and local_flake.path is absolute then a LocalFlakeError will be thrown
# If local_flake.copy_dir is not an absolute path then a LocalFlakeError will be thrown
# If local_flake.copy_dir is not set and one of the relative git roots is not found a LocalFlakeError will be thrown
def local_flake_path_and_root(local_flake: LocalFlake, qixos_config_dir: Path) -> tuple[Path, Path]:
    # FIXME: slightly complex logic, maybe we can refactor to make it clearer?
    if local_flake.copy_dir is not None:
        if not local_flake.copy_dir.is_absolute():
            raise LocalFlakeError.copy_dir_relative()
        elif local_flake.path.is_absolute():
            raise LocalFlakeError.path_absolute_with_copy_dir()
        else:
            return local_flake.path, local_flake.copy_dir
    else:
        if local_flake.path.is_absolute():
            root = _git_root(local_flake.path)
            return local_flake.path.relative_to(root), root
        else:
            return local_flake.path, _git_root(qixos_config_dir)


def tar(tardir: Path) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tar_path = tmp.name
        subprocess.run(
            ["tar", "-C", str(tardir), "-c", "."],
            stdout=tmp,
            check=True
        )
        return Path(tar_path)


def switch_protocol(tmpl_name: str, blob: ProtocolJson, tardirs: list[Path]):
    log.info("switch protocol beginning")
    log.info(f"calling {tmpl_name} {QREXEC_SERVICE}")
    qrexec_proc = subprocess.Popen(
        ["qrexec-client-vm", tmpl_name, f"{QREXEC_SERVICE}+"],
        stdin=subprocess.PIPE
    )
    assert qrexec_proc.stdin is not None
    blob_bytes = blob.model_dump_json().encode("utf-8")
    blob_length = len(blob_bytes)

    # 1. Send version
    qrexec_proc.stdin.write((f"{PROTOCOL_VERSION}" + '\n').encode())

    # 2. Send blob length
    qrexec_proc.stdin.write((str(blob_length) + '\n').encode())
    qrexec_proc.stdin.flush()

    log.info("sending json blob %s", blob_bytes)
    # 3. Send the json blob
    qrexec_proc.stdin.write(blob_bytes)
    qrexec_proc.stdin.flush()

    # 4. Each path in tardirs corresponds to the json_blob.tar_dirs in the same order
    for tardir in tardirs:
        log.info("trying to send tardir %s", tardir)
        # 5. Send a line containing an ascii encoded integer, B, of the number of bytes
        tar_size = os.path.getsize(tardir)
        log.info("sending directory size %s", tar_size)
        qrexec_proc.stdin.write((str(tar_size) + '\n').encode())
        qrexec_proc.stdin.flush()

        log.info("sending tar file %s", tardir)
        # 6. Send a stream of B bytes of a tar stream
        with open(tardir, "rb") as f:
            while chunk := f.read(8192):
                qrexec_proc.stdin.write(chunk)
        qrexec_proc.stdin.flush()

    log.info(f"waiting for qixos.Switch to finish on [{tmpl_name}]...")
    qrexec_proc.stdin.close()
    exit_code = qrexec_proc.wait()
    if exit_code != 0:
        if exit_code == OomKillerError.ERROR_CODE:
            raise OomKillerError(f"qixos.Switch failed likely due to an out-of-memory killer. Try to increase the RAM size of the {tmpl_name} VM.")

        log.error("qixos.Switch call for [%s] failed with: %s", tmpl_name, exit_code)
        raise QixosSwitchError(f"qixos.Switch call for [{tmpl_name}] failed with {exit_code}")

    log.info("[%s] qixos.Switch finished successfully", tmpl_name)


def ping_standalone(standalone_name: str, standalone_config: StandaloneVMConfig, qixos_config_dir: Path, update_lockfile: bool):
    log.info("ping standalone [%s]", standalone_name)
    tar_dirs = []
    archived_paths = []

    if standalone_config.local_flake is not None:
        # We are hashing here to get a name that will disambiguate different paths with the
        # same ending directory name.
        flake_path, tardir = local_flake_path_and_root(standalone_config.local_flake, qixos_config_dir)
        hash = hashlib.sha256(str(tardir).encode()).hexdigest()[:8]
        dir_name = f"{tardir.name}-{hash}"
        template_dirname = dir_name
        template_source = str(flake_path)
        template_output = standalone_config.local_flake.output

        if dir_name not in tar_dirs:
            archived_paths.append(tar(tardir))
            tar_dirs.append(dir_name)
    elif standalone_config.remote_flake is not None:
        template_dirname = None
        template_source = standalone_config.remote_flake.url
        template_output = standalone_config.remote_flake.output
    else:
        raise AssertionError("unreachable - neither a local or remote flake")

    # Treat a standalone as a template without appvms
    protocol_blob = ProtocolJson(
        template_dirname=template_dirname,
        template_flake=Flake(source=template_source, output=template_output),
        remote_appvms={},
        local_appvms={},
        tar_dirs=tar_dirs,
        update_lockfile=update_lockfile,
        standalone=True,
    )

    # Perform protocol
    switch_protocol(standalone_name, protocol_blob, archived_paths)

    for archive_path in archived_paths:
        os.unlink(archive_path)


def ping_template(tmpl_name: str, cluster_config: NubeClusterConfig, qixos_config_dir: Path, update_lockfile: bool):
    log.info("switching template [%s]", tmpl_name)
    tar_dirs = []
    archived_paths = []

    template = cluster_config.template
    if template.local_flake is not None:
        # We are hashing here to get a name that will disambiguate different paths with the
        # same ending directory name.
        flake_path, tardir = local_flake_path_and_root(template.local_flake, qixos_config_dir)
        hash = hashlib.sha256(str(tardir).encode()).hexdigest()[:8]
        dir_name = f"{tardir.name}-{hash}"
        template_dirname = dir_name
        template_source = str(flake_path)
        template_output = template.local_flake.output

        if dir_name not in tar_dirs:
            archived_paths.append(tar(tardir))
            tar_dirs.append(dir_name)
    elif template.remote_flake is not None:
        template_dirname = None
        template_source = template.remote_flake.url
        template_output = template.remote_flake.output
    else:
        raise AssertionError("unreachable - neither a local or remote flake")

    remote_appvms = {}
    local_appvms = {}
    for vm_name, nube in cluster_config.app_vms.items():
        if nube.local_flake is not None:
            flake_path, tardir = local_flake_path_and_root(nube.local_flake, qixos_config_dir)
            hash = hashlib.sha256(str(tardir).encode()).hexdigest()[:8]
            dir_name = f"{tardir.name}-{hash}"

            local_appvms[vm_name] = FlakeAndDir(
                dir_name=dir_name,
                flake=Flake(
                    source=str(flake_path),
                    output=nube.local_flake.output
                )
            )

            if dir_name not in tar_dirs:
                archived_paths.append(tar(tardir))
                tar_dirs.append(dir_name)
        elif nube.remote_flake is not None:
            remote_appvms[vm_name] = Flake(
                source=nube.remote_flake.url,
                output=nube.remote_flake.output
            )
        else:
            raise AssertionError("unreachable - neither a local or remote flake")

    protocol_blob = ProtocolJson(
        template_dirname=template_dirname,
        template_flake=Flake(source=template_source, output=template_output),
        remote_appvms=remote_appvms,
        local_appvms=local_appvms,
        tar_dirs=tar_dirs,
        update_lockfile=update_lockfile,
        standalone=False,
    )

    log.info("protocol_blob: %s", protocol_blob.model_dump_json(indent=2))

    # Perform protocol
    switch_protocol(tmpl_name, protocol_blob, archived_paths)

    for archive_path in archived_paths:
        os.unlink(archive_path)


def switch_templates(config: QixosConfig, app: QubesBase, flake_argument: str, only: list[str] | None = None, update_lockfile: bool = False):
    log.info("switch templates")
    log.debug("config: ", config)
    switched_something = False
    for tmpl_name, cluster_config in config.nube_clusters.items():
        if only is not None and tmpl_name not in only:
            # If only is set we only switch a subset of templates
            continue
        switched_something = True
        assert app.domains is not None
        vm = app.domains.get(tmpl_name)
        if vm is None:
            log.warning(f"Warning: template VM '{tmpl_name}' not found, skipping switch")
            continue

        qixos_config_dir = _flake_argument_to_qixos_config_dir(flake_argument)

        ping_template(tmpl_name, cluster_config, qixos_config_dir, update_lockfile)

        vm.shutdown()

    # TODO: Duplication needs to DRY
    for standalone_name, standalone_config in config.standalone_nubes.items():
        if only is not None and standalone_name not in only:
            continue
        switched_something = True
        assert app.domains is not None
        vm = app.domains.get(standalone_name)
        if vm is None:
            print(f"Warning: template VM '{standalone_name}' not found, skipping switch")
            continue

        qixos_config_dir = _flake_argument_to_qixos_config_dir(flake_argument)

        ping_standalone(standalone_name, standalone_config, qixos_config_dir, update_lockfile)

        vm.shutdown()

    if not switched_something and only is not None:
        print("Warning: found no nubes to switch")
