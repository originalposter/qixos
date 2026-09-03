"""Invariants VmProperties enforces before anything is written to qubes."""
import pytest

from qixos_rebuild.config import (
    AppVMConfig,
    StandaloneVMConfig,
    TemplateVMConfig,
    VmProperties,
    Volumes,
)
from pydantic import ValidationError

from qixos_rebuild.errors import ConfigError


def props(**kwargs):
    return VmProperties.model_validate({"label": "red", **kwargs})


def test_memory_above_maxmem_is_refused():
    """qubes takes both writes in any order and only bites at VM start."""
    with pytest.raises(ConfigError):
        props(memory=8000, maxmem=4000)


@pytest.mark.parametrize("kwargs", [
    {"memory": 600, "maxmem": 4000},
    {"memory": 600, "maxmem": 0},      # 0 disables ballooning, it is not a ceiling
    {"memory": 600},                   # maxmem unmanaged
    {"maxmem": 400},                   # memory unmanaged
    {"memory": 600, "maxmem": 600},    # equal is fine
])
def test_workable_combinations_are_accepted(kwargs):
    assert props(**kwargs) is not None


def test_an_unknown_property_is_refused():
    """A misspelled or not-yet-supported property, which pydantic would otherwise drop."""
    with pytest.raises(ValidationError):
        props(memroy=600)


@pytest.mark.parametrize("spelling", ["providesNetwork", "provides_network"])
def test_both_spellings_of_a_field_are_still_accepted(spelling):
    """populate_by_name makes these names rather than extras, so forbid does not bite."""
    assert props(**{spelling: True}).provides_network is True


def volumes(**kwargs):
    return Volumes.model_validate(kwargs)


@pytest.mark.parametrize("written,expected", [
    ("20 GiB", 20 * 1024 ** 3),
    ("20GiB", 20 * 1024 ** 3),
    ("20 gib", 20 * 1024 ** 3),
    ("20 GB", 20 * 1000 ** 3),      # decimal and binary units are not the same size
    ("3 MiB", 3 * 1024 ** 2),
    ("1.5 GiB", 1536 * 1024 ** 2),  # qubes takes bytes, so a fraction of a unit is fine
])
def test_a_size_is_read_as_bytes(written, expected):
    assert volumes(root=written).root == expected


@pytest.mark.parametrize("written", [
    "20",           # bytes would be a typo for something a billion times smaller
    20,             # what a nix config writing `root = 20;` sends
    20.5,
    "20 furlongs",
    "GiB",
    "",
    "20 GiB extra",
])
def test_an_unreadable_size_is_refused(written):
    with pytest.raises(ConfigError):
        volumes(root=written)


def test_an_explicit_null_leaves_the_volume_unmanaged():
    """What the nix config sends for a volume it mentions but does not size."""
    assert volumes(root=None).root is None


def test_an_unset_volume_is_unmanaged():
    assert volumes(root="20 GiB").private is None
    assert volumes().root is None


def nube(cls, **volume_sizes):
    return cls.model_validate({
        "properties": {"label": "red"},
        "volumes": volume_sizes,
        "remoteFlake": {"url": "github:example/nube", "output": "qixosAppConfigurations.x"},
    })


def test_an_appvm_cannot_set_a_root_size():
    """Its root is a snapshot of its template's, which qubes will not resize."""
    with pytest.raises(ConfigError):
        nube(AppVMConfig, root="20 GiB")


@pytest.mark.parametrize("cls", [TemplateVMConfig, StandaloneVMConfig])
def test_a_template_or_standalone_can(cls):
    assert nube(cls, root="20 GiB").volumes.root == 20 * 1024 ** 3


def test_an_appvm_can_still_set_a_private_size():
    assert nube(AppVMConfig, private="3 GiB").volumes.private == 3 * 1024 ** 3
