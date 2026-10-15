# `mkNubeSystem` function
#
# Makes the `nixosSystem` of one nube, a template or an AppVM, out of that nube's inner
# configuration. The generated flakes in a template call it: once for the template itself,
# and once in each AppVM's own flake.
#
# A cluster is made up of 1 template and a set of appvms that are based on that template.
# Each appVM defines its own complete configuration; what it shares with the template is the
# /nix/store, not the configuration itself. The template builds every dependent appVM's
# configuration into that shared store, which is what lets an appVM boot the template's root
# volume and then switch to its own configuration without building anything at runtime.
# The template's own configuration refers to none of them: qixos.Switch builds each as a
# separate step and leaves it under `activationDir`, so the template can be built first and
# an appVM that fails to build costs only itself.
#
# Note that in this model all of the /nix/store is shared, meaning that every AppVM can see every other AppVMs
# configuration. This does *not* mean that they can see each others home directories or live updates.
# nor does it mean that they have any way of changing the root system of another AppVM.
# It does mean that you should never put secret information inside the /nix/store. This is already very basic standard
# practice in the nix eco-system. They usually say "/nix/store is world-readable" and you should treat it like such (at least nube cluster readable)
#
# A template and its AppVMs get the same treatment here:
# 1. The core qix related modules.
# 2. The user specified system modules. Anything a user wants in their home directory is
# configured through these too, by importing home-manager as a nixos module.
# 3. A oneshot systemd job that runs on startup and, in an AppVM, switches from the template
# configuration it booted with to the configuration built for it. A template carries the job
# because its root volume is what an AppVM boots, and an AppVM carries it so that the unit
# does not change under the switch that is running it.

{ qixosCore }: { nixpkgs, ... }: nube:
let
  runQixosDir = "/run/qixos";
  # Directory our appVMs activation directories will be found. On the root volume, which
  # is what an appVM takes from its template. qixos.Switch fills it, so this must match
  # ACTIVATION_DIR in qixos_switch.py.
  activationDir = "/var/qixos/activation";

  basicQixCoreModules = import ./construct-qix-core-modules.nix { inherit qixosCore; };

  # Calls a function which returns a module.
  # This module sets up a systemd job that runs on VM boot
  # after all multi-user.target systemd jobs are done it runs an activation script specific to the VM
  # which switches it from template root to appVM root
  systemdBootstrapActivationModule =
    import ./bootstrap-systemd-activation.nix { inherit activationDir runQixosDir; };
in
nixpkgs.lib.nixosSystem {
  system = "x86_64-linux";
  modules = [ systemdBootstrapActivationModule ] ++ basicQixCoreModules ++ (nube.modules or []);
  specialArgs = nube.specialArgs or {};
}
