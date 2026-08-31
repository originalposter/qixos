"""Invariants VmProperties enforces before anything is written to qubes."""
import pytest

from qixos_rebuild.config import VmProperties
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
