"""What `apply` is told to change about existing VMs.

`calculate_reconcile_diffs` only reads attributes off the VM objects it is handed, so a
namespace stands in for a QubesVM and none of this needs qubes.
"""
from types import SimpleNamespace

import pytest

from qixos_rebuild import state
from qixos_rebuild.config import (
    QUBES_DEFAULT,
    QUBES_NONE,
    AppVMConfig,
    NubeClusterConfig,
    TemplateVMConfig,
    VmProperties,
)


def vm(is_default=True, **attrs):
    """A stand-in for a QubesVM, with defaults that match nothing the tests ask for."""
    defaults = dict(
        klass="AppVM", template="tmpl", netvm="sys-net",
        label="red", memory=400, maxmem=4000, vcpus=2, autostart=False,
        include_in_backups=True, qrexec_timeout=60, shutdown_timeout=60,
        provides_network=False, template_for_dispvms=False, default_dispvm=None,
    )
    stand_in = SimpleNamespace(**{**defaults, **attrs})
    # Whether a property is unset or pinned. Overridden by tests about "default".
    stand_in.property_is_default = lambda name: is_default
    return stand_in


def nube_config(cls=AppVMConfig, **properties):
    return cls(
        properties=VmProperties(**{"label": "red", **properties}),
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


def test_memory_reaches_the_diff():
    """The property `memory_matches_expected.py` asserts on.

    It was absent from VmProperties, so pydantic dropped it from the parsed config and an
    outer config declaring it was silently ignored.
    """
    diff = reconcile({"nube": vm(memory=400)}, {"nube": nube_config(memory=600)})

    assert diff.properties["nube"] == {"memory": 600}


def test_memory_that_already_matches_is_not_set_again():
    diff = reconcile({"nube": vm(memory=600)}, {"nube": nube_config(memory=600)})

    assert diff.properties == {}


def test_every_scalar_property_reaches_the_diff():
    """Each one goes through the generic loop, so this is really a guard on that loop.

    A property added to VmProperties but named differently from the qubesadmin one would
    read as "no change" forever rather than failing, since getattr falls back to None.
    """
    desired = dict(
        memory=600, maxmem=8000, vcpus=4, autostart=True,
        includeInBackups=False, qrexecTimeout=120, shutdownTimeout=90,
    )

    diff = reconcile({"nube": vm()}, {"nube": nube_config(**desired)})

    assert diff.properties["nube"] == {
        "memory": 600, "maxmem": 8000, "vcpus": 4, "autostart": True,
        "include_in_backups": False, "qrexec_timeout": 120, "shutdown_timeout": 90,
    }


def test_unset_properties_are_left_alone():
    """None means qixos does not manage it, not that it should be set to nothing."""
    diff = reconcile({"nube": vm()}, {"nube": nube_config()})

    assert diff.properties == {}


def test_an_undeclared_property_is_not_reverted():
    """Deliberate: a property qixos does not declare is one it does not touch.

    Reverting it instead would undo anything set by hand with qvm-prefs, on every apply,
    with no way to opt out. A qube's default is also not a fixed value, since memory and
    friends inherit from the template, so reverting means "inherit again" rather than any
    number the config could show you.

    netvm is the exception and behaves the other way: its field default is the string
    "default" rather than None, so omitting it does revert. That split is deliberate for
    now, not a rule every property follows.
    """
    was_set_by_an_earlier_apply = vm(vcpus=4)

    diff = reconcile({"nube": was_set_by_an_earlier_apply}, {"nube": nube_config()})

    assert diff.properties == {}


def test_asking_for_the_default_leaves_an_unset_property_alone():
    """It is already inheriting, so there is nothing to put back."""
    diff = reconcile({"nube": vm(netvm="sys-net", is_default=True)},
                     {"nube": nube_config(netvm=QUBES_DEFAULT)})

    assert diff.properties == {}


def test_asking_for_the_default_unpins_a_pinned_property():
    """Reads the same either way, and only starts differing when the default moves.

    This is the case the old name comparison got wrong: it saw "sys-net" on both sides
    and left the qube pinned, so it would not follow a later change to the system default.
    """
    diff = reconcile({"nube": vm(netvm="sys-net", is_default=False)},
                     {"nube": nube_config(netvm=QUBES_DEFAULT)})

    assert diff.properties["nube"] == {"netvm": QUBES_DEFAULT}


def test_default_dispvm_can_ask_for_the_default_too():
    """The point of one rule rather than a second _set_x per property."""
    diff = reconcile({"nube": vm(default_dispvm="some-dvm", is_default=False)},
                     {"nube": nube_config(defaultDispvm=QUBES_DEFAULT)})

    assert diff.properties["nube"] == {"default_dispvm": QUBES_DEFAULT}


def test_netvm_omitted_leaves_the_network_alone():
    """It used to default to QUBES_DEFAULT, so omitting it unpinned a qube's network."""
    diff = reconcile({"nube": vm(netvm="sys-net", is_default=False)}, {"nube": nube_config()})

    assert diff.properties == {}


def test_netvm_none_turns_the_network_off():
    """Distinct from omitting it, which is the whole point of the third state."""
    diff = reconcile({"nube": vm(netvm="sys-net")}, {"nube": nube_config(netvm=QUBES_NONE)})

    assert diff.properties["nube"] == {"netvm": QUBES_NONE}


def test_netvm_none_on_a_qube_that_already_has_no_network_is_a_no_op():
    diff = reconcile({"nube": vm(netvm=None)}, {"nube": nube_config(netvm=QUBES_NONE)})

    assert diff.properties == {}
