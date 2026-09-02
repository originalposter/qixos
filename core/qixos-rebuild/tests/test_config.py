"""Invariants VmProperties enforces before anything is written to qubes."""
import pytest

from qixos_rebuild.config import VmProperties
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
