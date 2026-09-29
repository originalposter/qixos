# Every module a nube needs.
#
# A file rather than a list inside the flake, because install/build-nix-template builds a
# template from these too. A second copy of the list is a copy that falls behind.
{
  imports = [
    ./appmenus.nix
    ./core.nix
    ./db.nix
    ./gui.nix
    ./networking.nix
    ./qrexec.nix
    ./ssh-host-keys.nix
    ./updates.nix
    ./usb.nix
  ];
}
