{
  description = "example nixos templatevm configuration";

  inputs = {
    nixpkgs.url = "nixpkgs/nixos-unstable";

    qubes-nixos-template = {
      url = "git+https://codeberg.org/originalposter/qixos";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    qubes-nixos-template,
    ...
  }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      overlays = [
        qubes-nixos-template.overlays.base
      ];
    };
  in {
    nixosConfigurations = {
      nixos = nixpkgs.lib.nixosSystem {
        inherit pkgs system;
        modules = [
          qubes-nixos-template.nixosModules.qubesModules
          qubes-nixos-template.nixosProfiles.basicQube
          ./configuration.nix
        ];
      };
    };
  };
}
