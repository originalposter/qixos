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
    StandaloneVMConfig,
    NubeClusterConfig,
    TemplateVMConfig,
    VmProperties,
)


GIB = 1024 ** 3


def vm(is_default=True, root=GIB, private=GIB, **attrs):
    """A stand-in for a QubesVM, with defaults that match nothing the tests ask for."""
    defaults = dict(
        klass="AppVM", template="tmpl", netvm="sys-net",
        label="red", memory=400, maxmem=4000, vcpus=2, autostart=False,
        include_in_backups=True, qrexec_timeout=60, shutdown_timeout=60,
        provides_network=False, template_for_dispvms=False, default_dispvm=None,
        volumes={
            "root": SimpleNamespace(size=root),
            "private": SimpleNamespace(size=private),
        },
    )
    stand_in = SimpleNamespace(**{**defaults, **attrs})
    # Whether a property is unset or pinned. Overridden by tests about "default".
    stand_in.property_is_default = lambda name: is_default
    return stand_in


def nube_config(cls=AppVMConfig, delete_on_removal=False, volumes=None, **properties):
    # deleteOnRemoval and volumes sit on the config, not on properties, and VmProperties
    # would drop them without a word.
    return cls(
        properties=VmProperties(**{"label": "red", **properties}),
        deleteOnRemoval=delete_on_removal,
        volumes=volumes or {},
        remoteFlake={"url": "github:example/nube", "output": "qixosAppConfigurations.x"},
    )


@pytest.fixture(autouse=True)
def no_removal_list(monkeypatch):
    """deleteOnRemoval is kept in a file this has no business reading."""
    monkeypatch.setattr(state, "should_delete_on_removal", lambda name: False)


def reconcile(managed, app_vms, standalones=None):
    cluster = NubeClusterConfig(
        appVms=app_vms,
        template=nube_config(TemplateVMConfig),
    )
    return state.calculate_reconcile_diffs(
        SimpleNamespace(default_netvm="sys-net"), managed, {"tmpl": cluster},
        standalones or {},
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
    """A pinned value equal to the default reads the same as an inherited one.

    Comparing names cannot tell them apart. The difference only shows once the system
    default moves and a pinned qube fails to follow it.
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
    """Saying nothing about netvm is distinct from asking for QUBES_NONE."""
    diff = reconcile({"nube": vm(netvm="sys-net", is_default=False)}, {"nube": nube_config()})

    assert diff.properties == {}


def test_netvm_none_turns_the_network_off():
    """Distinct from omitting it, which is the whole point of the third state."""
    diff = reconcile({"nube": vm(netvm="sys-net")}, {"nube": nube_config(netvm=QUBES_NONE)})

    assert diff.properties["nube"] == {"netvm": QUBES_NONE}


def test_netvm_none_on_a_qube_that_already_has_no_network_is_a_no_op():
    diff = reconcile({"nube": vm(netvm=None)}, {"nube": nube_config(netvm=QUBES_NONE)})

    assert diff.properties == {}


def test_a_standalone_gets_its_properties_too():
    """Standalones go through the same walk as cluster VMs."""
    diff = reconcile(
        {"alone": vm(vcpus=2)}, {},
        standalones={"alone": nube_config(StandaloneVMConfig, vcpus=4)},
    )

    assert diff.properties["alone"] == {"vcpus": 4}


def test_delete_on_removal_is_reported_when_it_differs(monkeypatch):
    """Both directions, since the qube's current setting is what it is compared against."""
    monkeypatch.setattr(state, "should_delete_on_removal", lambda name: False)
    turning_on = nube_config(delete_on_removal=True)
    assert reconcile({"nube": vm()}, {"nube": turning_on}).delete_on_removal == {"nube": True}

    monkeypatch.setattr(state, "should_delete_on_removal", lambda name: True)
    turning_off = nube_config(delete_on_removal=False)
    assert reconcile({"nube": vm()}, {"nube": turning_off}).delete_on_removal == {"nube": False}
    assert reconcile({"nube": vm()}, {"nube": turning_on}).delete_on_removal == {}


def test_a_volume_below_the_config_is_grown():
    diff = reconcile(
        {"nube": vm(private=GIB)},
        {"nube": nube_config(volumes={"private": "3 GiB"})},
    )

    assert diff.volumes == {"nube": {"private": 3 * GIB}}


def test_an_unmanaged_volume_is_not_touched():
    diff = reconcile(
        {"nube": vm(root=GIB, private=GIB)},
        {"nube": nube_config(volumes={"private": "3 GiB"})},
    )

    assert diff.volumes["nube"] == {"private": 3 * GIB}


def test_a_volume_above_the_config_is_not_shrunk():
    """A declared size is a floor. Reading a larger volume as a shrink request would not
    survive a second apply, since qubes rounds an allocation up to its pool's extent size
    and hands back a volume bigger than the number that asked for it.
    """
    diff = reconcile(
        {"nube": vm(private=8 * GIB)},
        {"nube": nube_config(volumes={"private": "3 GiB"})},
    )

    assert diff.volumes == {}


def test_a_template_grows_its_root():
    """The only way a cluster's AppVMs get a bigger root, since theirs is a snapshot."""
    diff = state.calculate_reconcile_diffs(
        SimpleNamespace(default_netvm="sys-net"),
        {"tmpl": vm(klass="TemplateVM", root=GIB)},
        {"tmpl": NubeClusterConfig(
            appVms={},
            template=nube_config(TemplateVMConfig, volumes={"root": "20 GiB"}),
        )},
        {},
    )

    assert diff.volumes == {"tmpl": {"root": 20 * GIB}}


def test_a_standalone_grows_too():
    diff = reconcile(
        {"alone": vm(klass="StandaloneVM", root=GIB)},
        {},
        {"alone": nube_config(StandaloneVMConfig, volumes={"root": "20 GiB"})},
    )

    assert diff.volumes == {"alone": {"root": 20 * GIB}}
