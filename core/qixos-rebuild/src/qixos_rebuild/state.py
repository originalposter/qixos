from qubesadmin.app import QubesBase
from qubesadmin.vm import QubesVM
from qubesadmin.exc import QubesDaemonAccessError
from .config import AppVMConfig, NubeClusterConfig, QixosConfig, StandaloneVMConfig, VmProperties
from .errors import DuplicateVmName, NoBaseTemplateError, QubesError, RenameError, NoNetVmError
from dataclasses import dataclass
import traceback
import os
import itertools
from typing import Any

type CurrentVM = QubesVM
type AppVmName = str
type TemplateVmName = str
type VmName = str
type PropertyName = str
type PropertyValue = Any


@dataclass
class ReconcileDiff:
    # Update the template of AppVMs
    app_vms_templates: dict[AppVmName, TemplateVmName]
    properties: dict[VmName, dict[PropertyName, PropertyValue]]
    delete_on_removal: dict[VmName, bool]


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
    # FIXME: If a VM is not found in managed we skip it with the assumption that
    # the reason we don't find it is because it has not yet been created.
    # We should make sure this is actually the reasonable assumption and handling of this case
    # we should also make sure the properties are set in the case of a created VM
    # we should apply DRY to setting properties.

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
        # Special case netvm because we need to do special handling of it. See `_set_netvm` for details
        if prop in ("netvm",):
            continue

        # FIXME: Lots of duplication here, we should clean it up
        # List through each cluster
        for desired_template_name, desired_nube_cluster_config in desired_nube_clusters.items():
            # List through the app VMs and the template VM of the cluster
            for vm_name, desired_vm_config in itertools.chain(
                desired_nube_cluster_config.app_vms.items(),
                [(desired_template_name, desired_nube_cluster_config.template)]
            ):
                if vm_name not in managed:
                    # Has not been created yet
                    continue
                curr_vm = managed[vm_name]
                desired = getattr(desired_vm_config.properties, prop, None)
                if desired is None:
                    continue
                actual = getattr(curr_vm, prop, None)
                if str(actual) != str(desired):
                    properties[vm_name] = {prop: desired}

        # List through each standalone VM
        for vm_name, desired_vm_config in desired_standalone_nubes.items():
            if vm_name not in managed:
                # Has not been created yet
                continue
            curr_vm = managed[vm_name]
            desired = getattr(desired_vm_config.properties, prop, None)
            if desired is None:
                continue
            actual = getattr(curr_vm, prop, None)
            if str(actual) != str(desired):
                properties[vm_name] = {prop: desired}

    # Set netvm
    for desired_template_name, desired_nube_cluster_config in desired_nube_clusters.items():
        # List through the app VMs and the template VM of the cluster
        for vm_name, desired_vm_config in itertools.chain(
            desired_nube_cluster_config.app_vms.items(),
            [(desired_template_name, desired_nube_cluster_config.template)]
        ):
            if vm_name not in managed:
                # Has not been created yet
                continue
            desired_netvm = desired_vm_config.properties.netvm
            curr_vm = managed[vm_name]
            curr_netvm = curr_vm.netvm

            # Hardcoding default template netvm to be None for the purposes of
            # checking if assignment is warranted and for printing. Should be fine.
            default_netvm = None if curr_vm.klass == "TemplateVM" else app.default_netvm
            # If desired is different from current and they are not both their default values
            if curr_netvm != desired_netvm and (desired_netvm != "default" or curr_netvm != default_netvm):
                properties[vm_name] = {"netvm": desired_netvm}

    for vm_name, desired_vm_config in desired_standalone_nubes.items():
        if vm_name not in managed:
            # Has not been created yet
            continue
        desired_netvm = desired_vm_config.properties.netvm
        curr_vm = managed[vm_name]
        curr_netvm = curr_vm.netvm

        # Hardcoding default template netvm to be None for the purposes of
        # checking if assignment is warranted and for printing. Should be fine.
        default_netvm = app.default_netvm
        # If desired is different from current and they are not both their default values
        if curr_netvm != desired_netvm and (desired_netvm != "default" or curr_netvm != default_netvm):
            properties[vm_name] = {"netvm": desired_netvm}

    delete_on_removal = {}
    # Set delete_on_removal
    for desired_template_name, desired_nube_cluster_config in desired_nube_clusters.items():
        # List through the app VMs and the template VM of the cluster
        for vm_name, desired_vm_config in itertools.chain(
            desired_nube_cluster_config.app_vms.items(),
            [(desired_template_name, desired_nube_cluster_config.template)]
        ):
            if vm_name not in managed:
                # Has not been created yet
                continue
            if desired_vm_config.delete_on_removal and not should_delete_on_removal(vm_name):
                delete_on_removal[vm_name] = True
            elif not desired_vm_config.delete_on_removal and should_delete_on_removal(vm_name):
                delete_on_removal[vm_name] = False

    for vm_name, desired_vm_config in desired_standalone_nubes.items():
        if vm_name not in managed:
            # Has not been created yet
            continue
        if desired_vm_config.delete_on_removal and not should_delete_on_removal(vm_name):
            delete_on_removal[vm_name] = True
        elif not desired_vm_config.delete_on_removal and should_delete_on_removal(vm_name):
            delete_on_removal[vm_name] = False

    return ReconcileDiff(app_vms_templates, properties, delete_on_removal)


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
    for tmpl_name, cluster_conf in config.nube_clusters.items():
        # Iterate through both template and app VMs
        for vm_name, vm_conf in itertools.chain(
            cluster_conf.app_vms.items(),
            [(tmpl_name, cluster_conf.template)]
        ):
            provides_network[vm_name] = vm_conf.properties.provides_network

    # Validate that
    # - there are not multiple of the same VM name
    # - netvms we depend on exist and provides network
    # - vm renamed from exists or two VMs rename from the same VM
    vm_names = set()
    renamed_from_vm_names = set()
    for tmpl_name, cluster_conf in config.nube_clusters.items():
        # Iterate through both template and app VMs
        for vm_name, vm_conf in itertools.chain(
            cluster_conf.app_vms.items(),
            [(tmpl_name, cluster_conf.template)]
        ):
            # Validate each VM appearing only once
            if vm_name in vm_names:
                raise DuplicateVmName(vm_name)
            vm_names.add(vm_name)

            # Validate netvms
            # - make sure the network VM exists
            # - the netvm will have the provides_network property
            vm_netvm = vm_conf.properties.netvm
            # the netvm is fine if it's either none or default
            if vm_netvm not in (None, "default"):
                in_qubes = vm_netvm in app.domains
                in_config = vm_netvm in provides_network
                if not in_qubes and not in_config:
                    # the netvm is not in our config nor in the system
                    raise NoNetVmError(vm_netvm, vm_name)
                if not in_config and in_qubes and not app.domains[vm_netvm].provides_network:
                    # the netvm is in the system and not in our config but will not provide network
                    raise NoNetVmError(vm_netvm, vm_name)
                if in_config and not provides_network[vm_netvm]:
                    # the netvm is in our config but will not provide network
                    raise NoNetVmError(vm_netvm, vm_name)

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
