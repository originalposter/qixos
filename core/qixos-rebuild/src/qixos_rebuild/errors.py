class NixError(Exception):
    pass


class QubesError(Exception):
    pass


class ConfigError(Exception):
    pass


class QixosSwitchError(Exception):
    pass


class RenameError(Exception):
    def __init__(self, error_msg: str) -> None:
        super().__init__("rename error:", error_msg)

    @classmethod
    def src_missing(cls, from_vm_name: str, to_vm_name: str) -> "RenameError":
        return cls(f"could not rename '{from_vm_name}' to '{to_vm_name}' due to '{from_vm_name}' being missing")

    @classmethod
    def duplicate_renames(cls, src_vm_name: str) -> "RenameError":
        return cls(f"multiple vms being renamed from '{src_vm_name}'")

    @classmethod
    def rename_to_itself(cls, vm_name: str) -> "RenameError":
        return cls(f"renaming '{vm_name}' to itself")


class NoBaseTemplateError(Exception):
    def __init__(self, base_template_name: str) -> None:
        super().__init__(f"base template {base_template_name} used to create templates from could not be found. Make sure the qixos admin VM has permission to list it.")


class NoNetVmError(Exception):
    def __init__(self, net_vm: str, using_vm_name: str) -> None:
        super().__init__(f"netvm '{net_vm}' could not be found. Make sure qixos admin VM has permission to list it. Required by '{using_vm_name}'")


class NoDispVmTemplateError(Exception):
    def __init__(self, dispvm_template: str, using_vm_name: str) -> None:
        super().__init__(f"defaultDispvm '{dispvm_template}' could not be found, or does not set templateForDispvms. Required by '{using_vm_name}'")


class DuplicateVmName(Exception):
    def __init__(self, duplicate_vm_name: str) -> None:
        super().__init__(f"found duplicate vms with the name '{duplicate_vm_name}'. Make sure only 1 VM has this name in the configuration.")


# TODO: Should specify which cluster this pertains to
class LocalFlakeError(Exception):
    def __init__(self, error_msg: str) -> None:
        super().__init__(error_msg)

    @classmethod
    def copy_dir_relative(cls) -> "LocalFlakeError":
        return cls("copyDir is not allowed to be a relative path")

    @classmethod
    def path_absolute_with_copy_dir(cls) -> "LocalFlakeError":
        return cls("path can not be an absolute path when copyDir is set")
