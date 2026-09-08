"""Removing qubes that other qubes still name.

Qubes refuses to remove one that another still points at, and `netvm` and
`defaultDispvm` are both such pointers. One apply can be removing both ends, in which case
only the order is wrong, or just the end being pointed at, in which case the config is
wrong and nothing should be removed at all.
"""
from types import SimpleNamespace

import pytest
from qubesadmin.exc import QubesVMInUseError

from qixos_rebuild import apply, state
from qixos_rebuild.errors import QubesError


def vm(inherits=(), **props):
    """A stand-in for a QubesVM.

    `inherits` names the properties this qube did not set, which read back the qubes
    default rather than anything this qube chose.
    """
    stand_in = SimpleNamespace(**{"netvm": None, "default_dispvm": None, **props})
    stand_in.property_is_default = lambda name: name in inherits
    return stand_in


def app_refusing(blocked_by):
    """A stand-in app whose deletes refuse while the qube blocking them is still there."""
    class Domains(dict):
        def __delitem__(self, name):
            blocker = blocked_by.get(name)
            if blocker is not None and blocker in self:
                raise QubesVMInUseError(f"{name} is in use by {blocker}")
            super().__delitem__(name)

    return SimpleNamespace(domains=Domains({name: vm() for name in blocked_by}))


# References a surviving qube makes, checked before anything is removed


def test_a_dispvm_template_a_kept_qube_names_is_reported():
    managed = {"dvm": vm(), "user": vm(default_dispvm="dvm")}

    assert state.vms_still_referenced(managed, {"dvm": managed["dvm"]}) == {
        "dvm": [("user", "default_dispvm")]
    }


def test_a_netvm_goes_through_the_same_check():
    """The property differs, the refusal from qubes does not."""
    managed = {"net": vm(), "user": vm(netvm="net")}

    assert state.vms_still_referenced(managed, {"net": managed["net"]}) == {
        "net": [("user", "netvm")]
    }


def test_removing_the_referrer_in_the_same_apply_is_fine():
    """The case that is only an ordering problem, not a configuration one."""
    managed = {"dvm": vm(), "user": vm(default_dispvm="dvm")}

    assert state.vms_still_referenced(managed, managed) == {}


def test_an_inherited_property_is_caught_as_a_default_not_as_a_reference():
    """Still an error, by the other route.

    `user` resolves a defaultDispvm without having named one, so it is not holding `dvm`
    down itself. What it does show is that `dvm` is the qubes-wide default, which is the
    harder problem and reported separately.
    """
    managed = {"dvm": vm(), "user": vm(default_dispvm="dvm", inherits=["default_dispvm"])}
    to_delete = {"dvm": managed["dvm"]}

    assert state.vms_still_referenced(managed, to_delete) == {}
    assert state.global_defaults_being_removed(managed, to_delete) == {
        "dvm": ("default_dispvm", 1)
    }


# The qubes-wide default, read back off whatever inherits it


def test_removing_the_global_default_is_reported_through_its_inheritors():
    """No admin.property.Get needed: an inheritor reads back the default itself."""
    managed = {
        "dvm": vm(),
        "a": vm(default_dispvm="dvm", inherits=["default_dispvm"]),
        "b": vm(default_dispvm="dvm", inherits=["default_dispvm"]),
    }

    assert state.global_defaults_being_removed(managed, {"dvm": managed["dvm"]}) == {
        "dvm": ("default_dispvm", 2)
    }


def test_a_qube_nothing_inherits_is_not_a_global_default():
    managed = {"dvm": vm(), "user": vm(default_dispvm="dvm")}

    assert state.global_defaults_being_removed(managed, {"dvm": managed["dvm"]}) == {}


# The order they actually come out in


def test_a_referenced_qube_is_deleted_after_the_one_naming_it():
    app = app_refusing({"dvm": "user", "user": None})

    # Worst order on purpose: the blocked one first.
    apply.delete_vms(app, ["dvm", "user"])

    assert dict(app.domains) == {}


def test_a_chain_of_references_unwinds():
    app = app_refusing({"a": "b", "b": "c", "c": None})

    apply.delete_vms(app, ["a", "b", "c"])

    assert dict(app.domains) == {}


def test_a_pass_that_deletes_nothing_is_an_error():
    """Two qubes naming each other cannot be removed in any order."""
    app = app_refusing({"a": "b", "b": "a"})

    with pytest.raises(QubesError):
        apply.delete_vms(app, ["a", "b"])

    assert set(app.domains) == {"a", "b"}
