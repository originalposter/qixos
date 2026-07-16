{ qixosCore }: input@{ directBuild ? null, ... }:
let
  nixpkgs = if directBuild != null then directBuild.nixpkgs else null;
  home-manager = if directBuild != null then directBuild.home-manager or null else null;

  # Get core modules needed for a qixos VM to function.
  # This does not include the module machinery used to switch to AppVMs.
  qixCoreModules = import ./construct-qix-core-modules.nix { inherit qixosCore; };
  homeManagerQixosModules = import ./construct-qix-home-modules.nix;
in
# Add lib.mkNubeCluster to the template so that it can be used by the generated flake
{
  config = input;

  # If the user passes `directBuild` with `nixpkgs` and/or `home-manager` then
  # we expose a direct build output for them to be able to switch to
  nixosConfigurations.default = if nixpkgs != null then nixpkgs.lib.nixosSystem {
    system = "x86_64-linux";
    modules = qixCoreModules ++ (input.rootConfiguration.modules or []);
    specialArgs = input.rootConfiguration.specialArgs or {};
  } else null;

  homeConfigurations.default = if home-manager != null then home-manager.lib.homeManagerConfiguration {
    pkgs = nixpkgs.legacyPackages.x86_64-linux;
    modules = homeManagerQixosModules
      ++ (input.homeConfiguration.modules or []);
    extraSpecialArgs = input.homeConfiguration.extraSpecialArgs or {};
  } else null;
}
