"""A template is built and activated first, then each AppVM on its own.

Evaluating a whole cluster in one nix process is what a template runs out of memory
doing, and it ties every AppVM to the weakest one: a single config that fails to evaluate
fails them all. Building the template first also means it is running its new
configuration while the AppVMs are fetched, which is what lets a template module such as
split-ssh serve those fetches.

Driven through main() with nix stood in for, so what is asserted is the commands a switch
runs and the status it exits with, which is all the admin ever learns of it.
"""
import json
import subprocess
import types

import pytest

from qixos_rebuild.errors import QixosSwitchError
from qixos_rebuild.qrexec import protocol, qixos_switch
from qixos_rebuild.qrexec.protocol import Flake, ProtocolJson
from qixos_rebuild import switch as admin_switch


def cluster(*appvms):
    return ProtocolJson(
        template_dirname=None,
        template_flake=Flake(source="github:example/cluster", output="qixosTemplateConfigurations.t"),
        remote_appvms={
            name: Flake(source=f"github:example/{name}", output="qixosAppConfigurations.a")
            for name in appvms
        },
        local_appvms={},
        tar_dirs=[],
        update_lockfile=False,
    )


TEMPLATE_REV = "0123456789abcdef0123456789abcdef01234567"


def is_rebuild(args):
    return args[0] == "nixos-rebuild"


def is_activation(args):
    return args[0].endswith("switch-to-configuration")


def is_build(args):
    return args[:2] == ["nix", "build"]


def builds(name):
    # Quoted, because a qube name may contain a dot and nix would read it as a path.
    return lambda args: is_build(args) and f'nixosConfigurations."{name}".' in args[2]


class Nix:
    """Stands in for subprocess.run, recording each command and failing those it is told to."""

    def __init__(self, failing, on_call=lambda args: None):
        self.calls = []
        self.failing = failing
        self.on_call = on_call

    def __call__(self, args, check=False, **kwargs):
        args = [str(arg) for arg in args]
        self.calls.append(args)
        self.on_call(args)
        if not self.failing(args):
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if check:
            raise subprocess.CalledProcessError(1, args, stderr=b"it broke")
        return subprocess.CompletedProcess(args, 1, b"", b"it broke")

    def index(self, matches):
        found = [i for i, args in enumerate(self.calls) if matches(args)]
        assert found, f"no such command among {self.calls}"
        return found[0]

    def ran(self, matches):
        return any(matches(args) for args in self.calls)


@pytest.fixture
def dirs(monkeypatch, tmp_path):
    """Point the switch at a scratch /var/qixos."""
    found = types.SimpleNamespace(
        flake=tmp_path / "template-flake",
        appvm_flakes=tmp_path / "appvm-flakes",
        activation=tmp_path / "activation",
    )
    monkeypatch.setattr(qixos_switch, "TEMPLATE_FLAKE_DIR", str(found.flake))
    monkeypatch.setattr(qixos_switch, "TEMPLATE_FLAKE_PATH", str(found.flake / "flake.nix"))
    # raising=False so that a tree without these fails on what it does, not on their names.
    monkeypatch.setattr(qixos_switch, "APPVM_FLAKES_DIR", found.appvm_flakes, raising=False)
    monkeypatch.setattr(qixos_switch, "ACTIVATION_DIR", found.activation, raising=False)
    return found


@pytest.fixture
def switch(monkeypatch, dirs):
    def run(blob, failing=lambda args: False):
        # Nix is stood in for, so the lock it would write for the template flake is too.
        def lock_template_flake(args):
            if args[:2] == ["nix", "flake"] and str(dirs.flake) in args:
                (dirs.flake / "flake.lock").write_text(json.dumps({"root": "root", "nodes": {
                    "root": {"inputs": {"template": "template"}},
                    "template": {"locked": {"type": "github", "owner": "example", "repo": "cluster", "rev": TEMPLATE_REV}},
                }}))

        nix = Nix(failing, lock_template_flake)
        monkeypatch.setattr(qixos_switch, "setup_logging", lambda: None)
        monkeypatch.setattr(qixos_switch, "read_protocol", lambda: blob)
        monkeypatch.setattr(qixos_switch.subprocess, "run", nix)
        try:
            qixos_switch.main()
        except SystemExit as exit:
            return nix, exit.code
        return nix, 0
    return run


def test_the_template_flake_names_no_appvm(switch, dirs):
    switch(cluster("a"))

    # Locking a flake fetches every input it names, so an AppVM named here is fetched
    # before the template has switched, and one that cannot be fetched fails the template.
    assert "github:example/a" not in (dirs.flake / "flake.nix").read_text()


def test_an_appvm_flake_names_the_template_by_what_it_was_locked_to(switch, dirs):
    switch(cluster("a"))

    flake = dirs.appvm_flakes / "a" / "flake.nix"
    assert flake.exists(), "no flake was generated for the AppVM"
    text = flake.read_text()
    assert "github:example/a" in text
    # By revision rather than by url, so the AppVM is built against the template that
    # was just built and not whatever that url resolves to when this flake is locked.
    assert f'rev = "{TEMPLATE_REV}";' in text
    for shared in ("nixpkgs", "qixCore"):
        assert f'appvm.inputs.{shared}.follows = "template/{shared}"' in text


def test_the_template_is_built_and_activated_before_an_appvm_is_touched(switch, dirs):
    nix, _ = switch(cluster("a"))

    rebuilt = nix.index(is_rebuild)
    activated = nix.index(is_activation)
    appvm = nix.index(lambda args: any(str(dirs.appvm_flakes) in arg for arg in args))
    assert rebuilt < activated < appvm
    # Locking is what fetches an AppVM's inputs, so that is the command that has to wait.
    assert nix.calls[appvm][:3] == ["nix", "flake", "lock"]


def test_each_appvm_is_built_by_a_nix_of_its_own(switch, dirs):
    nix, status = switch(cluster("a", "b"))

    assert status == 0
    for name in ("a", "b"):
        build = nix.calls[nix.index(builds(name))]
        # The out-link is what the AppVM looks up at boot, and what keeps its closure
        # from being garbage collected now that the template's does not refer to it.
        assert build[build.index("--out-link") + 1] == str(dirs.activation / name / "nixos")


def test_a_broken_appvm_does_not_stop_its_siblings(switch):
    nix, status = switch(cluster("a", "b"), failing=builds("a"))

    assert nix.ran(builds("b"))
    assert status == protocol.AppVmBuildError.ERROR_CODE


def test_an_appvm_named_with_a_dot_is_built(switch):
    """Qubes allows a dot in a name, where nix would split the attribute path."""
    nix, status = switch(cluster("work.dev"))

    assert nix.ran(builds("work.dev"))
    assert status == 0


def test_an_appvm_whose_flake_cannot_be_written_does_not_stop_its_siblings(switch, monkeypatch):
    write = qixos_switch.generate_appvm_flake

    def full_disk_for_a(name, *args):
        if name == "a":
            raise OSError(28, "No space left on device")
        return write(name, *args)

    monkeypatch.setattr(qixos_switch, "generate_appvm_flake", full_disk_for_a)
    nix, status = switch(cluster("a", "b"))

    assert nix.ran(builds("b"))
    assert status == protocol.AppVmBuildError.ERROR_CODE


def test_a_refused_activation_does_not_stop_the_builds(switch):
    """Switch inhibitors refuse a live activation that the next boot would accept."""
    nix, status = switch(cluster("a"), failing=is_activation)

    assert nix.ran(builds("a"))
    assert status == 0


def test_an_appvm_no_longer_in_the_cluster_loses_its_closure(switch, dirs):
    (dirs.activation / "gone").mkdir(parents=True)
    (dirs.activation / "gone" / "nixos").symlink_to("/nix/store/gone")

    switch(cluster("a"))

    assert not (dirs.activation / "gone").exists()


def test_the_admin_carries_on_past_a_cluster_whose_appvms_failed(monkeypatch):
    """The template did switch, so it is shut down like any other and the rest still run."""
    statuses = iter([protocol.AppVmBuildError.ERROR_CODE, 0])
    called = []

    def qrexec(args, **kwargs):
        called.append(args[1])
        return types.SimpleNamespace(stdin=types.SimpleNamespace(
            write=lambda data: None, flush=lambda: None, close=lambda: None,
        ), wait=lambda: next(statuses))

    monkeypatch.setattr(subprocess, "Popen", qrexec)

    shut_down = []
    template = types.SimpleNamespace(
        template=types.SimpleNamespace(
            local_flake=None,
            remote_flake=types.SimpleNamespace(url="github:example/cluster", output="t"),
        ),
        app_vms={},
    )
    config = types.SimpleNamespace(
        nube_clusters={"first": template, "second": template},
        standalone_nubes={},
    )
    domains = {
        name: types.SimpleNamespace(shutdown=lambda name=name: shut_down.append(name))
        for name in config.nube_clusters
    }

    with pytest.raises(QixosSwitchError) as raised:
        admin_switch.switch_templates(config, types.SimpleNamespace(domains=domains), "./outer#x")

    assert called == ["first", "second"]
    assert shut_down == ["first", "second"]
    assert "first" in str(raised.value)


def test_the_shipped_repos_are_not_inside_the_template_flake():
    """The template's flake is read as a path flake, which nix copies whole into the store.

    Every localFlake shipped over, .git included, would otherwise be copied along with it
    on every switch.
    """
    assert not qixos_switch.LOCAL_REPOS_DIR.is_relative_to(qixos_switch.TEMPLATE_FLAKE_DIR)


def test_a_template_without_the_flake_directory_still_switches(switch, dirs):
    """A fresh template has none of /var/qixos until its first switch makes it."""
    nix, status = switch(cluster("a"))

    assert status == 0
    assert (dirs.flake / "flake.nix").exists()
