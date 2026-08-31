"""qixos.Switch is a one-way channel: nothing the template writes reaches the admin.

A template evaluates and builds the inner configs of every AppVM in its cluster, and those
are not trusted (desiderata 3). The exit status is the only thing the admin is meant to
learn from a switch, so the service's stdout, which is the one stream qrexec connects back
to the caller, is closed rather than inherited.

The handle below refuses to be read from, so a switch_protocol that reached for the far
side fails here naming what it touched instead of passing against a mock that happened to
provide it.
"""
import io
import subprocess

import pytest

from qixos_rebuild.errors import QixosSwitchError
from qixos_rebuild.qrexec.protocol import Flake, ProtocolJson, SWITCH_LOG_PATH
from qixos_rebuild.switch import switch_protocol

BLOB = ProtocolJson(
    template_dirname=None,
    template_flake=Flake(source="github:example/nube", output="qixosTemplateConfigurations.x"),
    remote_appvms={},
    local_appvms={},
    tar_dirs=[],
    update_lockfile=False,
)


class Handle:
    """Stands in for the Popen handle, answering only stdin and wait."""

    def __init__(self, returncode):
        self.accessed = set()
        self._stdin = io.BytesIO()
        self._returncode = returncode

    def __getattr__(self, name):
        self.accessed.add(name)
        if name == "stdin":
            return self._stdin
        if name == "wait":
            return lambda: self._returncode
        raise AssertionError(
            f"switch_protocol touched {name!r} on the qrexec handle. The exit status is "
            "the only thing the admin may learn from a template."
        )


class FakeQrexec:
    """Records how qrexec-client-vm was opened, and hands back a Handle."""

    def __init__(self, returncode):
        self.handle = Handle(returncode)
        self.args = None
        self.kwargs = None

    def __call__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        return self.handle


@pytest.fixture
def qrexec(monkeypatch):
    def install(returncode=0):
        fake = FakeQrexec(returncode)
        monkeypatch.setattr(subprocess, "Popen", fake)
        return fake
    return install


def test_both_service_streams_are_closed(qrexec):
    fake = qrexec()

    switch_protocol("test-template", BLOB, [])

    # qrexec carries both: MSG_DATA_STDOUT and MSG_DATA_STDERR (qrexec.h), and
    # qrexec-client-vm has --filter-escape-chars-stderr because what arrives there is the
    # remote's, not its own.
    for stream in ("stdout", "stderr"):
        assert fake.kwargs.get(stream) is subprocess.DEVNULL, (
            f"the template's {stream} is inherited, so whatever it writes there lands on "
            "the admin's terminal"
        )


def test_nothing_but_the_exit_status_is_read(qrexec):
    fake = qrexec()

    switch_protocol("test-template", BLOB, [])

    # stdin is the outbound half of the protocol. wait is the exit status. Nothing else on
    # that handle is a channel the admin is allowed to have.
    assert fake.handle.accessed == {"stdin", "wait"}


def test_a_failed_switch_raises_and_says_where_to_look(qrexec):
    qrexec(returncode=1)

    with pytest.raises(QixosSwitchError) as raised:
        switch_protocol("test-template", BLOB, [])

    # The reason never crosses, so the error has to name the template and the log on it.
    assert "test-template" in str(raised.value)
    assert SWITCH_LOG_PATH in str(raised.value)


def test_a_clean_switch_returns(qrexec):
    qrexec(returncode=0)

    switch_protocol("test-template", BLOB, [])
