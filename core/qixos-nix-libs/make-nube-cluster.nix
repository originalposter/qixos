# `mkNubeClusterWith` function
#
# Kept for one caller: a qixos.Switch from before each nube had a generated flake of its
# own. That one generates a single flake calling `mkNubeCluster { template; apps; }` and
# builds `nixosConfigurations.template` out of it, and it is the code that carries out the
# switch which brings a template onto this version. Without this that switch fails, and
# the template can never install a qixos.Switch that calls `mkNubeSystem` instead.
#
# A template runs such a qixos.Switch until its first switch onto this version, and a new
# template is cloned from the base template, so this can go once no base template in use
# was built before `mkNubeSystem` existed.

{ qixosCore }: { nixpkgs, ... }: { template, apps ? {}, ... }:
let
  mkNubeSystem = import ./make-nube-system.nix { inherit qixosCore; } { inherit nixpkgs; };
in
{
  nixosConfigurations = { template = mkNubeSystem template; } // builtins.mapAttrs (_: mkNubeSystem) apps;
}
