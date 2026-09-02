import qubesadmin
from qubesadmin.app import QubesBase
from qubesadmin.vm import QubesVM
from qubesadmin.exc import QubesVMNotStartedError
from . import state
from .state import ReconcileDiff, mark_delete_on_removal, get_managed_vms, validate
from .config import QUBES_DEFAULT, QUBES_NONE, QixosConfig, NubeClusterConfig, AppVMConfig, StandaloneVMConfig, VmProperties


# Internal function for setting the netvm property.
# Needs to deal with default values and starting up stopped network VMs
def _set_netvm(app: QubesBase, desired_netvm: str | None, curr_vm: QubesVM):
    # None is a config that says nothing about netvm, so there is nothing to do. Whether
    # a change is warranted is decided by the diff; this only carries it out.
    if desired_netvm is None:
        return

    old_netvm = curr_vm.netvm
    if desired_netvm == QUBES_NONE:
        assignment = None
    elif desired_netvm == QUBES_DEFAULT:
        assignment = qubesadmin.DEFAULT
    else:
        assignment = desired_netvm

    try:
        curr_vm.netvm = assignment
    except QubesVMNotStartedError:
        assert app.domains is not None
        # FIXME: Need to deal with the vm being paused rather than stopped
        # FIXME: Could this exception be triggered by not an chained netvm not being started?
        app.domains[desired_netvm].start()
        curr_vm.netvm = assignment
    print(f"  '{curr_vm.name}': netvm {old_netvm} -> {desired_netvm}")


def rename_vm(
    app: QubesBase,
    from_name: str,
    to_name: str,
):
    # FIXME: We don't want the rename process to have ignore_errors=True
    # because losing data in the clone and then deleting the original VM
    # could be disastrous. Therefore we gate this API until we have figured
    # out the below bug.
    raise NotImplementedError("rename functionality is not available due to blocking on a potential bug in upstream qubes")
    assert app.domains is not None
    from_vm = app.domains[from_name]
    # There is, as far as I know, no API for renaming qubes.
    # The qubes management GUI seems to clone a VM and delete the old one
    # FIXME: There seems to be a bug related to the admin.vm.notes.Get+ call.
    # This appears in the create_template_vm call as well.
    # We should investigate upstream.
    app.clone_vm(from_vm, to_name, from_vm.klass)
    del app.domains[from_name]


# TODO: Deduplicate
def create_template_vm(
    app: QubesBase,
    tmpl_name: str,
    nube_cluster: NubeClusterConfig,
    base_template: str,
):
    print(f"Creating template '{tmpl_name}' based on '{base_template}'")
    # FIXME: This entire cloning process is a bit unclear. It for some reason requires a start of
    # the original cloned VM. It also requires a qvm-appmenus binary to copy appmenus, this might not actually
    # be sensemaking for non-dom0 mgmt VMs. Look into how this all works.
    assert app.domains is not None
    vm = app.clone_vm(
        app.domains[base_template],
        tmpl_name,
        "TemplateVM",
        # TODO: Probably should not ignore errors, but doing so right now because the clone
        # asks for a bunch of stuff we don't want to need to give permission for like get.Notes
        ignore_errors=True,
    )
    # TODO: Set properties
    vm.label = app.get_label(nube_cluster.template.properties.label)
    _set_netvm(app, nube_cluster.template.properties.netvm, vm)
    mark_delete_on_removal(tmpl_name, nube_cluster.template.delete_on_removal)


def create_vm(
    app: QubesBase,
    vm_name: str,
    vm_config: AppVMConfig,
    tmpl_name: str,
):
    print(f"Creating '{vm_name}'")
    vm = app.add_new_vm(
        "AppVM",
        name=vm_name,
        label=vm_config.properties.label,
        template=tmpl_name,
    )

    # TODO: Set properties
    _set_netvm(app, vm_config.properties.netvm, vm)

    mark_delete_on_removal(vm_name, vm_config.delete_on_removal)


def create_standalone_vm(
    app: QubesBase,
    vm_name: str,
    vm_config: StandaloneVMConfig,
    base_template: str,
):
    print(f"Creating standalone '{vm_name}' based on '{base_template}'")
    # FIXME: This entire cloning process is a bit unclear. It for some reason requires a start of
    # the original cloned VM. It also requires a qvm-appmenus binary to copy appmenus, this might not actually
    # be sensemaking for non-dom0 mgmt VMs. Look into how this all works.
    assert app.domains is not None
    vm = app.clone_vm(
        app.domains[base_template],
        vm_name,
        "StandaloneVM",
        # TODO: Probably should not ignore errors, but doing so right now because the clone
        # asks for a bunch of stuff we don't want to need to give permission for like get.Notes
        ignore_errors=True,
    )
    # TODO: Set properties
    vm.label = app.get_label(vm_config.properties.label)
    _set_netvm(app, vm_config.properties.netvm, vm)
    mark_delete_on_removal(vm_name, vm_config.delete_on_removal)


def delete_vm(app: QubesBase, vm_name: str):
    print(f"Deleting '{vm_name}'")
    assert app.domains is not None
    del app.domains[vm_name]


def reconcile_vms(app: QubesBase, reconcile_diff: ReconcileDiff):
    assert app.domains is not None
    # Set template for app VMs
    for appvm, template in reconcile_diff.app_vms_templates.items():
        curr_vm = app.domains[appvm]
        print(f"  '{appvm}': template {curr_vm.template} -> {template}")
        curr_vm.template = template

    # Set properties
    # Go through each property and set it for each VM, both templates and App VMs
    # The ordering of properties matters since they are interdependent.
    # The order we go through is the order described in the `VmProperties` class.
    for prop in list(VmProperties.__annotations__):
        # Special case netvm because we need to do special handling of it. See `_set_netvm` for details
        if prop in ("netvm",):
            continue
        for vm_name, update_prop in reconcile_diff.properties.items():
            if prop in update_prop:
                curr_vm = app.domains[vm_name]
                actual = getattr(curr_vm, prop, None)
                desired = update_prop[prop]
                print(f"  '{vm_name}': {prop} {actual} -> {desired}")
                # "default" asks for the qubes default rather than for a qube of that
                # name. Only string properties can carry it: an int field rejects it at
                # parse time.
                setattr(curr_vm, prop,
                        qubesadmin.DEFAULT if desired == QUBES_DEFAULT else desired)

    # Set netvm
    for vm_name, update_prop in reconcile_diff.properties.items():
        prop = "netvm"
        if prop in update_prop:
            curr_vm = app.domains[vm_name]
            desired = update_prop[prop]
            _set_netvm(app, desired, curr_vm)

    # Set delete_on_removal
    for vm_name, delete_on_removal in reconcile_diff.delete_on_removal.items():
        print(f"  '{vm_name}': delete on removal {not delete_on_removal} -> {delete_on_removal}")
        mark_delete_on_removal(vm_name, delete_on_removal)


def apply(app: QubesBase, config: QixosConfig, base_template: str, qixos_config_flake: str):
    validate(app, config, qixos_config_flake)
    managed = get_managed_vms(app, config.management_tag)
    vm_changes = state.diff(app, config, managed)

    for from_name, to_name in vm_changes.vms_to_rename.items():
        rename_vm(app, from_name, to_name)

    for tmpl_name, tmpl_config in vm_changes.templatevms_to_create.items():
        create_template_vm(app, tmpl_name, tmpl_config, base_template)

    for vm_name, (tmpl_name, vm_config) in vm_changes.appvms_to_create.items():
        create_vm(app, vm_name, vm_config, tmpl_name)

    for standalone_name, standalone_config in vm_changes.standalonevms_to_create.items():
        create_standalone_vm(app, standalone_name, standalone_config, base_template)

    for vm_name in vm_changes.appvms_to_delete.keys():
        delete_vm(app, vm_name)

    for vm_name in vm_changes.templatevms_to_delete.keys():
        delete_vm(app, vm_name)

    for vm_name in vm_changes.standalonevms_to_delete.keys():
        delete_vm(app, vm_name)

    # Recomputed rather than reusing vm_changes.reconcile_diff, which was calculated
    # before the creates above and therefore skips every VM this run made: those VMs are
    # not in `managed` yet, so their properties would only be applied by the next apply.
    # Creation sets label, netvm and deleteOnRemoval; everything else arrives here.
    managed = get_managed_vms(app, config.management_tag)
    reconcile_vms(app, state.calculate_reconcile_diffs(
        app, managed, config.nube_clusters, config.standalone_nubes,
    ))
