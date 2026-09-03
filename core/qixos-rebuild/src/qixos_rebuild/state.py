from qubesadmin.app import QubesBase
from qubesadmin.vm import QubesVM
from qubesadmin.exc import QubesDaemonAccessError
from .config import QUBES_DEFAULT, QUBES_NONE, AppVMConfig, NubeClusterConfig, QixosConfig, StandaloneVMConfig, VmConfigMixin, VmProperties
from .errors import DuplicateVmName, NoBaseTemplateError, NoDispVmTemplateError, QubesError, RenameError, NoNetVmError
from dataclasses import dataclass
import traceback
import os
from collections.abc import Iterator
from typing import Any

type CurrentVM = QubesVM
type AppVmName = str
type TemplateVmName = str
type VmName = str
type PropertyName = str
type PropertyValue = Any
type VolumeName = str


@dataclass
class ReconcileDiff:
    # Update the template of AppVMs
    app_vms_templates: dict[AppVmName, TemplateVmName]
    properties: dict[VmName, dict[PropertyName, PropertyValue]]
    delete_on_removal: dict[VmName, bool]
    # Target sizes in bytes, only for volumes that are below what the config asks for
    volumes: dict[VmName, dict[VolumeName, int]]


@dataclass
class VmChanges:
    # from : to
    vms_to_rename: dict[VmName, VmName]
    templatevms_to_create: dict[TemplateVmName, NubeClusterConfig]
    appvms_to_create: dict[AppVmName, tuple[TemplateVmName, AppVMConfig]]
    standalonevms_to_create: dict[VmName, StandaloneVMConfig]
    reconcile_diff: ReconcileDiff
    templatevms_to_delete: dict[TemplateVmName, QubesVM]
    appvms_to_delete: dict[AppVmName, QubesVM]
    standalonevms_to_delete: dict[VmName, QubesVM]


# FIXME: path is too hardcoded
_DELETE_ON_REMOVAL_LIST_PATH = "/home/user/.config/qixos/.vms_to_delete_on_removal_from_config"


def _read_removal_list() -> list[str]:
    try:
        with open(_DELETE_ON_REMOVAL_LIST_PATH) as f:
            return f.read().splitlines()
    except FileNotFoundError:
        os.makedirs(os.path.dirname(_DELETE_ON_REMOVAL_LIST_PATH), exist_ok=True)
        with open(_DELETE_ON_REMOVAL_LIST_PATH, 'w') as f:
            f.write('')
        return []


def should_delete_on_removal(vm_name: str) -> bool:
    return vm_name in _read_removal_list()


def mark_delete_on_removal(vm_name: str, should_delete: bool):
    removal_list = _read_removal_list()
    if vm_name in removal_list and not should_delete:
        removal_list.remove(vm_name)
    elif vm_name not in removal_list and should_delete:
        removal_list.append(vm_name)

    with open(_DELETE_ON_REMOVAL_LIST_PATH, 'w') as f:
        f.write('\n'.join(removal_list))


def get_managed_vms(app: QubesBase, management_tag: str) -> dict[str, QubesVM]:
    try:
        return {
            vm.name: vm
            for vm in (app.domains or [])
            if management_tag in vm.tags
        }
    except QubesDaemonAccessError as e:
        traceback.print_exc()
        raise QubesError("lacking permission to list qubes") from e


def calculate_reconcile_diffs(
        app: QubesBase,
        managed: dict[str, QubesVM],
        desired_nube_clusters: dict[TemplateVmName, NubeClusterConfig],
        desired_standalone_nubes: dict[VmName, StandaloneVMConfig]
) -> ReconcileDiff:
    # A VM not in `managed` does not exist yet, so there is nothing to compare against and
    # nothing to reconcile. `apply` calls this a second time after creating VMs, with
    # `managed` re-read, which is what gets a new VM its properties on the same run.

    # Set template for app VMs
    app_vms_templates = {}
    for desired_template_name, desired_nube_cluster_config in desired_nube_clusters.items():
        for app_vm_name, _ in desired_nube_cluster_config.app_vms.items():
            if app_vm_name not in managed:
                # Has not been created yet
                continue
            curr_app_vm = managed[app_vm_name]
            if curr_app_vm.template != desired_template_name:
                app_vms_templates[app_vm_name] = desired_template_name

    # Set properties
    # Go through each property and set it for each VM, both templates and App VMs
    # The ordering of properties matters since they are interdependent.
    # The order we go through is the order described in the `VmProperties` class.
    properties = {}
    for prop in list(VmProperties.__annotations__):
        for vm_name, desired_vm_config, curr_vm in _managed_vms(
                managed, desired_nube_clusters, desired_standalone_nubes):
            desired = getattr(desired_vm_config.properties, prop, None)
            if desired is None:
                continue
            if _wants_a_change(curr_vm, prop, desired):
                properties.setdefault(vm_name, {})[prop] = desired

    # Set delete_on_removal
    delete_on_removal = {}
    for vm_name, desired_vm_config, _ in _managed_vms(
            managed, desired_nube_clusters, desired_standalone_nubes):
        if desired_vm_config.delete_on_removal != should_delete_on_removal(vm_name):
            delete_on_removal[vm_name] = desired_vm_config.delete_on_removal

    volumes = _volumes_to_grow(managed, desired_nube_clusters, desired_standalone_nubes)

    return ReconcileDiff(app_vms_templates, properties, delete_on_removal, volumes)


def _volumes_to_grow(
        managed: dict[VmName, CurrentVM],
        clusters: dict[TemplateVmName, NubeClusterConfig],
        standalones: dict[VmName, StandaloneVMConfig],
) -> dict[VmName, dict[VolumeName, int]]:
    """Volumes the config wants bigger than they are.

    A declared size is a floor, so one already at or above it yields nothing. Treating a
    larger volume as a shrink request would not survive a second apply: qubes rounds an
    allocation up to its pool's extent size, so a volume can come back bigger than the
    number that produced it, and growing one by hand is a thing people do.
    """
    to_grow = {}
    for vm_name, desired_vm_config, curr_vm in _managed_vms(managed, clusters, standalones):
        for volume, desired in desired_vm_config.volumes.model_dump().items():
            if desired is None:
                continue
            if desired > curr_vm.volumes[volume].size:
                to_grow.setdefault(vm_name, {})[volume] = desired
    return to_grow


def _declared_vms(
        clusters: dict[TemplateVmName, NubeClusterConfig],
        standalones: dict[VmName, StandaloneVMConfig],
) -> Iterator[tuple[VmName, VmConfigMixin]]:
    """Every VM these declare, whatever its class."""
    for tmpl_name, cluster_conf in clusters.items():
        yield from cluster_conf.app_vms.items()
        yield tmpl_name, cluster_conf.template
    yield from standalones.items()


def _managed_vms(
        managed: dict[VmName, CurrentVM],
        clusters: dict[TemplateVmName, NubeClusterConfig],
        standalones: dict[VmName, StandaloneVMConfig],
) -> Iterator[tuple[VmName, VmConfigMixin, CurrentVM]]:
    """Declared VMs that exist, paired with the qube as it stands.

    One that is absent has not been created yet, so there is nothing to compare against.
    """
    for vm_name, desired in _declared_vms(clusters, standalones):
        if vm_name in managed:
            yield vm_name, desired, managed[vm_name]


def _wants_a_change(curr_vm: QubesVM, prop: str, desired: PropertyValue) -> bool:
    """Whether `prop` on this VM is not already what the config asks for.

    `"default"` asks for the qubes default, which is a state rather than a value: a qube
    pinned to a name that currently equals the default reads the same as one inheriting
    it, and only starts differing when the default later moves. The admin API reports
    which it is, in the same property.Get the value itself comes from.
    """
    if desired is None:
        # Not managed by this config. The generic loop skips these before calling, but
        # netvm has its own pass and reaches here.
        return False
    if desired == QUBES_DEFAULT:
        return not curr_vm.property_is_default(prop)
    if desired == QUBES_NONE:
        return getattr(curr_vm, prop, None) is not None
    return str(getattr(curr_vm, prop, None)) != str(desired)


def _refers_to_a_capable_vm(
        app: QubesBase,
        referenced: str,
        capability: str,
        declared: dict[VmName, bool | None],
) -> bool:
    """Whether `referenced` will exist and have `capability` set once this config applies.

    A reference may point at a qube already on the system or at one this config declares,
    and the config wins: it is what the qube is about to become.
    """
    assert app.domains is not None
    in_config = referenced in declared
    if in_config:
        return bool(declared[referenced])
    if referenced in app.domains:
        return bool(getattr(app.domains[referenced], capability, False))
    return False


# Raises exceptions if the configuration is found to be invalid
def validate(app: QubesBase, config: QixosConfig, qixos_config_flake: str):
    # TODO: Validate that if local flake urls are ever used then `qixos_config_flake` points to a local url
    # Validate that the base template exists
    assert app.domains is not None
    if config.base_template not in app.domains:
        raise NoBaseTemplateError(config.base_template)

    # Need to build a list of all VMs to see if they provide network.
    # This dict contains all the VMs in our config
    # We need to do 2 passes because a former VM might reference a netvm
    # defined later in the config.
    provides_network = {}
    template_for_dispvms = {}
    for vm_name, vm_conf in _declared_vms(config.nube_clusters, config.standalone_nubes):
        provides_network[vm_name] = vm_conf.properties.provides_network
        template_for_dispvms[vm_name] = vm_conf.properties.template_for_dispvms

    # Validate that
    # - there are not multiple of the same VM name
    # - netvms we depend on exist and provides network
    # - vm renamed from exists or two VMs rename from the same VM
    vm_names = set()
    renamed_from_vm_names = set()
    for vm_name, vm_conf in _declared_vms(config.nube_clusters, config.standalone_nubes):
        # Validate each VM appearing only once
        if vm_name in vm_names:
            raise DuplicateVmName(vm_name)
        vm_names.add(vm_name)

        # Validate netvms
        # - make sure the network VM exists
        # - the netvm will have the provides_network property
        vm_netvm = vm_conf.properties.netvm
        # only a name is a reference: None is unmanaged, and the two sentinels
        # name no qube
        if vm_netvm not in (None, QUBES_DEFAULT, QUBES_NONE):
            if not _refers_to_a_capable_vm(app, vm_netvm, "provides_network", provides_network):
                raise NoNetVmError(vm_netvm, vm_name)

        # Validate defaultDispvm the same way: it must exist and be willing to be a
        # disposable template.
        vm_dispvm = vm_conf.properties.default_dispvm
        if vm_dispvm is not None:
            if not _refers_to_a_capable_vm(app, vm_dispvm, "template_for_dispvms", template_for_dispvms):
                raise NoDispVmTemplateError(vm_dispvm, vm_name)

        # Validate rename logic
        vm_rename_from = vm_conf.rename_from
        if vm_rename_from is not None:
            if vm_rename_from == vm_name:
                raise RenameError.rename_to_itself(vm_name)

            if vm_rename_from not in app.domains:
                raise RenameError.src_missing(vm_rename_from, vm_name)

            if vm_rename_from in renamed_from_vm_names:
                raise RenameError.duplicate_renames(vm_rename_from)

            renamed_from_vm_names.add(vm_rename_from)


def diff(app: QubesBase, config: QixosConfig, managed: dict[str, QubesVM]) -> VmChanges:
    desired_template_vms = {
        template_name: cluster_config
        for template_name, cluster_config in config.nube_clusters.items()
    }

    desired_app_vms = {
        vm_name: (tmpl_name, vm_config)
        for tmpl_name, cluster in config.nube_clusters.items()
        for vm_name, vm_config in cluster.app_vms.items()
    }

    desired_standalone_vms = {
        standalone_name: standalone_config
        for standalone_name, standalone_config in config.standalone_nubes.items()
    }

    vms_to_rename = {}
    for tmpl_name, cluster_conf in desired_template_vms.items():
        rename_from = cluster_conf.template.rename_from
        if rename_from is not None:
            vms_to_rename[rename_from] = tmpl_name
            if rename_from not in managed:
                raise RenameError(f"{rename_from} does not exist and can not be renamed to {tmpl_name}")

    for app_name, (_, conf) in desired_app_vms.items():
        rename_from = conf.rename_from
        if rename_from is not None:
            vms_to_rename[rename_from] = app_name
            if rename_from not in managed:
                raise RenameError(f"{rename_from} does not exist and can not be renamed to {app_name}")

    for standalone_name, standalone_config in desired_standalone_vms.items():
        rename_from = standalone_config.rename_from
        if rename_from is not None:
            vms_to_rename[rename_from] = standalone_name
            if rename_from not in managed:
                raise RenameError(f"{rename_from} does not exist and can not be renamed to {standalone_name}")

    templatevms_to_create = {
        name: cfg
        for name, cfg in desired_template_vms.items()
        if name not in managed
        and name not in vms_to_rename.values()
    }

    appvms_to_create = {
        name: cfg
        for name, cfg in desired_app_vms.items()
        if name not in managed
        and name not in vms_to_rename.values()
    }

    standalonevms_to_create = {
        name: cfg
        for name, cfg in desired_standalone_vms.items()
        if name not in managed
        and name not in vms_to_rename.values()
    }

    reconcile_diff = calculate_reconcile_diffs(
        app,
        managed,
        {
            name: desired_template_vms[name]
            for name in desired_template_vms
            if name in managed
        },
        {
            name: desired_standalone_vms[name]
            for name in desired_standalone_vms
            if name in managed
        }
    )

    templatevms_to_delete = {
        name: vm
        for name, vm in managed.items()
        if name not in desired_app_vms
        and name not in desired_template_vms
        and name not in desired_standalone_vms
        and should_delete_on_removal(name)
        and vm.klass == "TemplateVM"
    }

    appvms_to_delete = {
        name: vm
        for name, vm in managed.items()
        if name not in desired_app_vms
        and name not in desired_template_vms
        and name not in desired_standalone_vms
        and should_delete_on_removal(name)
        and vm.klass == "AppVM"
    }

    standalonevms_to_delete = {
        name: vm
        for name, vm in managed.items()
        if name not in desired_standalone_vms
        and name not in desired_template_vms
        and name not in desired_standalone_vms
        and should_delete_on_removal(name)
        and vm.klass == "StandaloneVM"
    }

    changes = VmChanges(
        vms_to_rename,
        templatevms_to_create,
        appvms_to_create,
        standalonevms_to_create,
        reconcile_diff,
        templatevms_to_delete,
        appvms_to_delete,
        standalonevms_to_delete
    )

    return changes
