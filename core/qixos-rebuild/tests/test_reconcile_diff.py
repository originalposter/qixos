"""What `apply` is told to change about existing VMs.

`calculate_reconcile_diffs` only reads attributes off the VM objects it is handed, so a
namespace stands in for a QubesVM and none of this needs qubes.
"""
from types import SimpleNamespace

import pytest

from qixos_rebuild import state
from qixos_rebuild.config import (
    AppVMConfig,
    NubeClusterConfig,
    TemplateVMConfig,
    VmProperties,
)


def vm(**attrs):
    """A stand-in for a QubesVM, with defaults that match nothing the tests ask for."""
    defaults = dict(
        klass="AppVM", template="tmpl", netvm="sys-net",
        label="red", provides_network=False, template_for_dispvms=False,
    )
    return SimpleNamespace(**{**defaults, **attrs})


def nube_config(cls=AppVMConfig, **properties):
    return cls(
        properties=VmProperties(**{"label": "red", "netvm": "sys-net", **properties}),
        remoteFlake={"url": "github:example/nube", "output": "qixosAppConfigurations.x"},
    )


@pytest.fixture(autouse=True)
def no_removal_list(monkeypatch):
    """deleteOnRemoval is kept in a file this has no business reading."""
    monkeypatch.setattr(state, "should_delete_on_removal", lambda name: False)


def reconcile(managed, app_vms):
    cluster = NubeClusterConfig(
        appVms=app_vms,
        template=nube_config(TemplateVMConfig),
    )
    return state.calculate_reconcile_diffs(
        SimpleNamespace(default_netvm="sys-net"), managed, {"tmpl": cluster}, {},
    )


def test_every_changed_property_is_reported():
    """Two properties on one VM means two entries, not whichever was checked last.
    """
    diff = reconcile(
        {"nube": vm(provides_network=False, template_for_dispvms=False)},
        {"nube": nube_config(providesNetwork=True, templateForDispvms=True)},
    )

    assert diff.properties["nube"] == {
        "provides_network": True,
        "template_for_dispvms": True,
    }


def test_netvm_does_not_displace_the_others():
    """netvm is collected in its own pass, which was the other half of the same bug."""
    diff = reconcile(
        {"nube": vm(netvm="sys-firewall", provides_network=False)},
        {"nube": nube_config(netvm="sys-net", providesNetwork=True)},
    )

    assert diff.properties["nube"] == {"provides_network": True, "netvm": "sys-net"}


def test_matching_properties_are_left_alone():
    diff = reconcile(
        {"nube": vm(provides_network=True)},
        {"nube": nube_config(providesNetwork=True)},
    )

    assert diff.properties == {}


def test_a_vm_that_does_not_exist_yet_is_skipped():
    """It has nothing to compare against. `apply` reconciles again once it exists."""
    diff = reconcile({}, {"nube": nube_config(providesNetwork=True)})

    assert diff.properties == {}
