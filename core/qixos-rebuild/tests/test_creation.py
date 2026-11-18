"""How `apply` hands out netvms when a nube is another qube's netvm.

dom0 refuses a netvm that does not provide network, and `providesNetwork` only arrives in
the reconcile pass, so a nube serving another created in the same apply cannot be named
at creation. Nor can one created later in the same loop.
"""
from types import SimpleNamespace

import pytest

from qixos_rebuild import apply
from qixos_rebuild.state import ReconcileDiff
from qixos_rebuild.config import QUBES_DEFAULT, QUBES_NONE, AppVMConfig, VmProperties


def created_with(netvm, monkeypatch):
    """The netvm `create_vm` leaves on a new qube whose config names `netvm`."""
    monkeypatch.setattr(apply, "mark_delete_on_removal", lambda name, delete: None)
    new = SimpleNamespace(name="user", netvm=QUBES_DEFAULT)
    app = SimpleNamespace(add_new_vm=lambda *args, **kwargs: new)
    config = AppVMConfig(
        properties=VmProperties(label="red", netvm=netvm),
        remoteFlake={"url": "github:example/nube", "output": "qixosAppConfigurations.x"},
    )
    apply.create_vm(app, "user", config, "tmpl")
    return new.netvm


def test_a_named_netvm_waits_for_the_reconcile_pass(monkeypatch):
    """Created with none rather than the default, so a nube that never reaches the
    reconcile pass is left off the network instead of on the default netvm."""
    assert created_with("router", monkeypatch) is None


@pytest.mark.parametrize("netvm,expected", [(QUBES_NONE, None), (None, QUBES_DEFAULT)])
def test_none_and_unmanaged_netvms_are_set_at_creation(netvm, expected, monkeypatch):
    assert created_with(netvm, monkeypatch) == expected


def test_halted_qubes_get_their_netvm_before_running_ones():
    """A running qube's assignment starts its netvm, and qubes starts that one's netvm in
    turn. So every halted qube in a chain of netvms is wired first, whatever order the
    diff lists them in: here a running provider is repointed at a new provider that has
    a new provider of its own."""
    assigned = []

    class Vm(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "netvm":
                assigned.append(self.name)
            super().__setattr__(name, value)

        def is_running(self):
            return self.running

    app = SimpleNamespace(domains={
        "running": Vm(name="running", netvm="sys-net", provides_network=True, running=True),
        "first": Vm(name="first", netvm=None, provides_network=True, running=False),
        "second": Vm(name="second", netvm=None, provides_network=True, running=False),
    })
    diff = ReconcileDiff(
        app_vms_templates={}, delete_on_removal={}, volumes={},
        properties={
            "running": {"netvm": "first"},
            "first": {"netvm": "second"},
            "second": {"netvm": "sys-net"},
        },
    )
    apply.reconcile_vms(app, diff)
    assert assigned[-1] == "running"
