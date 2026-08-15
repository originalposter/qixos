{ qixosCore }: input@{ directBuild ? null, ... }:
let
  nixpkgs = if directBuild != null then directBuild.nixpkgs else null;

  # Get core modules needed for a qixos VM to function.
  # This does not include the module machinery used to switch to AppVMs.
  qixCoreModules = import ./construct-qix-core-modules.nix { inherit qixosCore; };
in
{
  config = input;

  # If the user passes `directBuild` with `nixpkgs` then we expose a direct build
  # output for them to be able to switch to
  nixosConfigurations.default = if nixpkgs != null then nixpkgs.lib.nixosSystem {
    system = "x86_64-linux";
    modules = qixCoreModules ++ (input.modules or []);
    specialArgs = input.specialArgs or {};
  } else null;
}
