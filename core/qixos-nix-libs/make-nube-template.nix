{ qixosCore }: { nixpkgs }: input:
let
  # The template config injects its own preferred nixpkgs
  mkNubeSystem = import ./make-nube-system.nix { inherit qixosCore; } { inherit nixpkgs; };
  mkNubeCluster = import ./make-nube-cluster.nix { inherit qixosCore; } { inherit nixpkgs; };
  # Get core modules needed for a qixos VM to function.
  # This does not include the module machinery used to switch to AppVMs.
  qixCoreModules = import ./construct-qix-core-modules.nix { inherit qixosCore; };
in
# Add lib.mkNubeSystem to the template so that it can be used by the generated flakes
{
  config = input;
  lib.mkNubeSystem = mkNubeSystem;
  # For a qixos.Switch that predates mkNubeSystem. See make-nube-cluster.nix.
  lib.mkNubeCluster = mkNubeCluster;
  # We expose a nixosConfiguration so that the user can use `nixos-rebuild` directly to switch to our template.
  nixosConfigurations.default = nixpkgs.lib.nixosSystem {
    system = "x86_64-linux";
    modules = qixCoreModules ++ input.modules;
    specialArgs = input.specialArgs or {};
  };
}
