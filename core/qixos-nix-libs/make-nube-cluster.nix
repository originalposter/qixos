# `mkNubeClusterWith` function
#
# One of the primary entrypoints in QixOS for when making clusters of nix based qubes (nubes).
# A cluster is made up of 1 template and a set of appvms that are based on that template.
# Each appVM defines its own complete configuration; what it shares with the template is the
# /nix/store, not the configuration itself. The template builds every dependent appVM's
# configuration into that shared store, which is what lets an appVM boot the template's root
# volume and then switch to its own configuration without building anything at runtime.
#
# Note that in this model all of the /nix/store is shared, meaning that every AppVM can see every other AppVMs
# configuration. This does *not* mean that they can see each others home directories or live updates.
# nor does it mean that they have any way of changing the root system of another AppVM.
# It does mean that you should never put secret information inside the /nix/store. This is already very basic standard
# practice in the nix eco-system. They usually say "/nix/store is world-readable" and you should treat it like such (at least nube cluster readable)
# 
# This function returns another function with some parameters set, call it "mkNubeCluster".
# `mkNubeCluster` returns one `nixosSystem` configuration for the TemplateVM and one for each AppVM.
#
# ### How to use it: ###
# In your nube cluster flake you have an output.
# 
# nubeCluster = mkNubeCluster {
# TODO: ...
# }
#
# TODO: Actually we could make the `nixos-rebuild` tooling just use qixosNubeCluster.nixosConfigurations.template instead I think.
# nixosConfigurations.template = self.qixosNubeCluster.nixosConfigurations.template;
#
# qixosNubeCluster will expose these endpoints
# - qixosNubeCluster.nixosConfigurations.template
# - qixosNubeCluster.nixosConfigurations.<appvm-name>
#
# ### How it works: ###
# This function is supposed to create multiple nixosConfigurations.
#
# This function is a bit tricky because it needs to build all of the AppVM specific configuration
# and then it needs to reference these in a systemd startup script that it uses to switch
# the appVM from the template configuration (that it boots with) to the AppVM configuration.
# Desiderata:
# 1. We want all templates to have some core qix related modules on it.
# 2. We want the template to contain the user specified root system modules.
# 3. We want the AppVM to contain the user specified system modules. Anything a user wants in their
# home directory is configured through these too, by importing home-manager as a nixos module.
# 4. We want the template and ideally the AppVM to have a oneshot systemd job that runs on startup and switches to the correct
# AppVM derivation.

{ qixosCore }: { nixpkgs, ... }: { template, apps, ... }:
let

  runQixosDir = "/run/qixos";
  # Directory our appVMs activation directories will be found
  activationDir = "${runQixosDir}/activation";

  basicQixCoreModules = import ./construct-qix-core-modules.nix { inherit qixosCore; };
  userTemplateModules = template.modules;

  # Calls a function which returns a module.
  # This module sets up a systemd job that runs on VM boot
  # after all multi-user.target systemd jobs are done it runs an activation script specific to the VM
  # which switches it from template root to appVM root
  systemdBootstrapActivationModule =
    let 
      systemdBootstrapModuleFactory = import ./bootstrap-systemd-activation.nix;
    in
      systemdBootstrapModuleFactory { inherit activationDir runQixosDir; appVmNames = builtins.attrNames apps; };

  coreModules = [ systemdBootstrapActivationModule ] ++ basicQixCoreModules;

  # Attrs mapping AppVM name to the configuration that should be activated for that AppVM
  # This contains all of the core modules needed too.
  appVmDerivations = builtins.mapAttrs
    (appVmName: appVmConfig:
      nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = coreModules ++ (appVmConfig.modules or []);
        specialArgs = appVmConfig.specialArgs or {};
      }
    )
    apps;

  # Calls a function which returns a module which inside the template 
  # links the appropriate appVM activation directory in a well defined
  # directory that this appVM can find.
  # This is used for bootstrapping together with the systemd bootstrap job
  templateBootstrapActivationLinkingModule =
    let 
      activationDirectoryLinkingFactory = import ./bootstrap-template-linking.nix;
    in 
      activationDirectoryLinkingFactory { inherit activationDir appVmDerivations; };

  # These are all the modules that the template nixOS configuration will load
  totalTemplateModules = [
      templateBootstrapActivationLinkingModule
    ]
    ++ coreModules
    ++ userTemplateModules;
in
{
  nixosConfigurations = {
      template = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = totalTemplateModules;
        specialArgs = template.specialArgs or {};
      };
    }
    // appVmDerivations;
}
