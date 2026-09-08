"""A switch killed for memory is reported as one.

The kernel usually takes the nix build underneath `nixos-rebuild` rather than
`nixos-rebuild` itself, so the process qixos.Switch waits on exits with an ordinary
non-zero status that says nothing about memory. Reading the kernel's own count of what it
killed is what separates the two, and the distinction is the whole point: one failure
tells the reader to give the template more memory, the other tells them nothing.
"""
import signal
import subprocess

import pytest

from qixos_rebuild.qrexec import qixos_switch
from qixos_rebuild.qrexec.protocol import NixosRebuildError, OomKillerError


def runner(rebuild_returncode):
    """Stands in for subprocess.run: the lock succeeds, the rebuild fails."""
    def run(args, **kwargs):
        if args[0] == "nixos-rebuild":
            raise subprocess.CalledProcessError(
                rebuild_returncode, args, stderr=b"build failed"
            )
        return subprocess.CompletedProcess(args, 0, b"", b"")
    return run


def switch(monkeypatch, rebuild_returncode, kills):
    """Drive build_and_switch with a known exit status and kernel kill count."""
    readings = iter(kills)
    monkeypatch.setattr(qixos_switch, "oom_kills", lambda: next(readings))
    monkeypatch.setattr(qixos_switch.subprocess, "run", runner(rebuild_returncode))
    qixos_switch.build_and_switch(update_lockfile=False, standalone=True)


def test_a_kill_during_the_build_is_an_oom_however_nixos_rebuild_exited(monkeypatch):
    """The case the old check could not see: the kernel took a child, not the parent."""
    with pytest.raises(OomKillerError):
        switch(monkeypatch, rebuild_returncode=1, kills=[7, 8])


def test_nixos_rebuild_killed_outright_is_still_an_oom(monkeypatch):
    with pytest.raises(OomKillerError):
        switch(monkeypatch, rebuild_returncode=-signal.SIGKILL, kills=[7, 7])


def test_a_failure_with_no_kill_is_not_an_oom(monkeypatch):
    """Otherwise every broken config would be reported as an out-of-memory."""
    with pytest.raises(NixosRebuildError):
        switch(monkeypatch, rebuild_returncode=1, kills=[7, 7])


def test_a_kernel_that_will_not_say_falls_back_to_the_exit_status(monkeypatch):
    with pytest.raises(NixosRebuildError):
        switch(monkeypatch, rebuild_returncode=1, kills=[None, None])


def test_oom_kills_reads_the_counter(tmp_path, monkeypatch):
    vmstat = tmp_path / "vmstat"
    vmstat.write_text("nr_dirty 12\noom_kill 4\npgfault 99\n")
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: vmstat.open())

    assert qixos_switch.oom_kills() == 4
