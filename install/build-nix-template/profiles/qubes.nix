{
  config,
  lib,
  pkgs,
  ...
}: {
  services.qubes.qrexec.enable = true;
  services.qubes.gui.enable = true;
  services.qubes.networking.enable = true;
  services.qubes.usb.enable = true;

  fonts.enableDefaultPackages = true;

  # When running in PVH mode, the qubes init script will bind mount the kernel modules here
  systemd.tmpfiles.rules = [
    "d /lib/modules 0755 root root"
  ];
  # When running in PVH mode, the qubes init script expects /sbin/init to exist
  boot.loader.initScript.enable = true;

  # Don't use the GRUB 2 boot loader since it conflicts with initScript.enable
  boot.loader.grub.enable = false;

  # In Qubes PVH mode, dom0 controls the kernel cmdline and passes "ro".
  # The systemd initrd (default since ~mid-2025 nixpkgs) mounts /sysroot
  # read-only and skips the remount-rw step, so NixOS activation cannot
  # write /run/current-system. Use the shell-based initrd instead, which
  # unconditionally remounts root rw before running activation.
  boot.initrd.systemd.enable = false;
}
