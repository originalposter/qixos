"""Cross-VM references a config makes, checked before anything is written.

A reference may point at a qube already on the system or at one this config declares, and
the config wins, since it is what that qube is about to become.
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
    QixosConfig,
    TemplateVMConfig,
    VmProperties,
)
from qixos_rebuild.errors import NoDispVmTemplateError, NoNetVmError


def nube_config(cls=AppVMConfig, **properties):
    return cls(
        properties=VmProperties.model_validate({"label": "red", **properties}),
        remoteFlake={"url": "github:example/nube", "output": "qixosAppConfigurations.x"},
    )


def config(standalones=None, **app_vms):
    return QixosConfig(
        nubeClusters={"tmpl": NubeClusterConfig(
            appVms=app_vms, template=nube_config(TemplateVMConfig),
        )},
        standaloneNubes=standalones or {},
        managementTag="created-by-qixos-admin",
        baseTemplate="base",
    )


def app(**domains):
    """Qubes as it stands, plus the base template validate insists on."""
    return SimpleNamespace(domains={"base": SimpleNamespace(), **domains})


def validate(app_, cfg):
    return state.validate(app_, cfg, "./somewhere#config")


def test_a_dispvm_template_declared_in_this_config_is_accepted():
    """It does not exist yet. The config is what it is about to become."""
    validate(app(), config(
        vault=nube_config(templateForDispvms=True),
        user=nube_config(defaultDispvm="vault"),
    ))


def test_a_dispvm_template_already_on_the_system_is_accepted():
    validate(
        app(existing=SimpleNamespace(template_for_dispvms=True)),
        config(user=nube_config(defaultDispvm="existing")),
    )


def test_a_dispvm_template_that_does_not_exist_is_refused():
    with pytest.raises(NoDispVmTemplateError):
        validate(app(), config(user=nube_config(defaultDispvm="nowhere")))


def test_a_dispvm_template_without_the_flag_is_refused():
    """Pointing at a qube that will not agree to be one is the interesting failure."""
    with pytest.raises(NoDispVmTemplateError):
        validate(app(), config(
            vault=nube_config(templateForDispvms=False),
            user=nube_config(defaultDispvm="vault"),
        ))


def test_a_default_dispvm_of_default_names_no_qube_to_check():
    """QUBES_DEFAULT asks for whatever dom0 has as the default, resolved there not here."""
    validate(app(), config(user=nube_config(defaultDispvm=QUBES_DEFAULT)))


def test_a_default_dispvm_of_none_names_no_qube_to_check():
    """QUBES_NONE asks for no disposable base at all, so there is nothing to resolve."""
    validate(app(), config(user=nube_config(defaultDispvm=QUBES_NONE)))


def test_an_undeclared_default_dispvm_is_not_checked():
    validate(app(), config(user=nube_config()))


def test_netvm_goes_through_the_same_check():
    with pytest.raises(NoNetVmError):
        validate(app(), config(user=nube_config(netvm="nowhere")))

    validate(app(), config(
        router=nube_config(providesNetwork=True),
        user=nube_config(netvm="router"),
    ))


def standalone(**properties):
    return nube_config(StandaloneVMConfig, **properties)


def test_a_standalone_is_validated_too():
    with pytest.raises(NoNetVmError):
        validate(app(), config(standalones={"alone": standalone(netvm="nowhere")}))

    with pytest.raises(NoDispVmTemplateError):
        validate(app(), config(standalones={"alone": standalone(defaultDispvm="nowhere")}))


def test_a_standalone_cannot_reuse_a_cluster_name():
    from qixos_rebuild.errors import DuplicateVmName

    with pytest.raises(DuplicateVmName):
        validate(app(), config(nube=nube_config(), standalones={"nube": standalone()}))


def test_a_standalone_can_be_referenced_by_a_cluster_vm():
    """The other half: it is now in the map references resolve against."""
    validate(app(), config(
        user=nube_config(netvm="router"),
        standalones={"router": standalone(providesNetwork=True)},
    ))
