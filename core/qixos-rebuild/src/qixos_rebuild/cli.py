import sys
import logging
import argparse
import os
from pydantic import ValidationError
import qubesadmin
from .config import eval_config
from .apply import apply
from .switch import switch_templates
from .errors import ConfigError, DuplicateVmName, NixError, NoBaseTemplateError, NoNetVmError, OomKillerError, QixosSwitchError, QubesError, RenameError, LocalFlakeError
from .state import get_managed_vms, diff, validate


logging.basicConfig(
    level=os.environ.get("QIXOS_LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)


log = logging.getLogger("qixos")


def cmd_apply(args, app):
    log.info("apply")
    config = eval_config(args.flake)
    apply(app, config, config.base_template, args.flake)
    if not args.no_switch:
        switch_templates(config, app, args.flake, update_lockfile=args.update)


def cmd_switch(args, app):
    log.info("switch")
    config = eval_config(args.flake)
    switch_templates(config, app, args.flake, only=args.only, update_lockfile=args.update)


def cmd_diff(args, app):
    log.info("diff")
    config = eval_config(args.flake)
    managed = get_managed_vms(app, config.management_tag)
    validate(app, config, args.flake)
    vm_changes = diff(app, config, managed)

    print("Templates to create:")
    if not vm_changes.templatevms_to_create:
        print("  none")
    else:
        for name in vm_changes.templatevms_to_create.keys():
            print(f"  + {name}")

    print("Appvms to create:")
    if not vm_changes.appvms_to_create:
        print("  none")
    else:
        for name in vm_changes.appvms_to_create.keys():
            print(f"  + {name}")

    print("Standalones to create:")
    if not vm_changes.standalonevms_to_create:
        print("  none")
    else:
        for name in vm_changes.standalonevms_to_create.keys():
            print(f"  + {name}")

    print("To delete:")
    if not vm_changes.appvms_to_delete and not vm_changes.templatevms_to_delete and not vm_changes.standalonevms_to_delete:
        print("  none")
    else:
        for name in vm_changes.appvms_to_delete.keys():
            print(f"  - {name}")
        for name in vm_changes.templatevms_to_delete.keys():
            print(f"  - {name}")
        for name in vm_changes.standalonevms_to_delete.keys():
            print(f"  - {name}")

    print("To reconcile:")
    print("  templates:")
    if not vm_changes.reconcile_diff.app_vms_templates:
        print("  none")
    else:
        for name, template in vm_changes.reconcile_diff.app_vms_templates.items():
            print(f"    ~ {name} -> {template}")

    print("  properties:")
    if not vm_changes.reconcile_diff.properties:
        print("  none")
    else:
        for vm_name, props in vm_changes.reconcile_diff.properties.items():
            print(f"    ~ {vm_name}")
            for name, value in props.items():
                print(f"       {name} -> {value}")

    print("  delete on removal:")
    if not vm_changes.reconcile_diff.delete_on_removal:
        print("  none")
    else:
        for vm_name, delete_on_removal in vm_changes.reconcile_diff.delete_on_removal.items():
            print(f"    ~ {vm_name} -> {delete_on_removal}")


def main():
    parser = argparse.ArgumentParser(prog="qixos-rebuild")
    parser.add_argument("--flake", required=True, help="URL to qixosConfigurations flake")
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="Apply config and switch templates")
    p_apply.add_argument("--no-switch", action="store_true", help="Skip template switching")
    p_apply.add_argument(
        "--update",
        action="store_true",
        help="Update the generated lockfile in each template"
    )
    p_apply.set_defaults(func=cmd_apply)

    p_switch = sub.add_parser("switch", help="Switch templates without applying VM config")
    p_switch.add_argument(
        "--only",
        type=lambda s: s.split(","),
        default=None,
        help="Comma separated list of templates to switch"
    )
    p_switch.add_argument(
        "--update",
        action="store_true",
        help="Update the generated lockfile in each template"
    )
    p_switch.set_defaults(func=cmd_switch)

    p_diff = sub.add_parser("diff", help="Show what would change without applying")
    p_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args()

    app = qubesadmin.Qubes()

    try:
        args.func(args, app)
    except NixError as e:
        print("failed to evaluate nix expression", e, file=sys.stderr)
    except QubesError as e:
        print("lacking qubes permissions", e, file=sys.stderr)
    except RenameError as e:
        print(e, file=sys.stderr)
    except NoBaseTemplateError as e:
        print(e, file=sys.stderr)
    except NoNetVmError as e:
        print(e, file=sys.stderr)
    except DuplicateVmName as e:
        print(e, file=sys.stderr)
    except ConfigError as e:
        print(e, file=sys.stderr)
    except LocalFlakeError as e:
        print(e, file=sys.stderr)
    except ValidationError as e:
        # TODO: THIS SHOULD BE MADE WAY MORE READABLE
        print(f"Invalid qixos configuration:\n{e}", file=sys.stderr)
    except QixosSwitchError as e:
        print(e, file=sys.stderr)
    except OomKillerError as e:
        print(e, file=sys.stderr)
    else:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
