{
  description = "nixos templatevm configurations";

  inputs = {
    nixpkgs.url = "nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
    ...
  }: let
    lib = nixpkgs.lib;
    system = "x86_64-linux";
    # Core's own overlay, not a copy of it. Anything core's modules expect from `pkgs`
    # has to be here too, and a copy would not stay that way.
    qubesPackages = import ../../core/qubes-pkgs/overlay.nix;

    pkgs = import nixpkgs {
      inherit system;
      overlays = [
        qubesPackages
      ];
    };
  in rec {
    overlays.default = qubesPackages;
    nixosModules.default = ../../core/qubes-modules;
    nixosProfiles.default = {
      config,
      lib,
      pkgs,
      ...
    }: {
      imports = [
        ../../core/qubes-modules/basic-qube-profile.nix
      ];
    };
    nixosConfigurations = {
      nixos =
        lib.nixosSystem
        {
          inherit pkgs system;
          modules = [
            self.nixosModules.default
            self.nixosProfiles.default
            ./examples/configuration.nix
          ];
        };
      iso = lib.nixosSystem {
        inherit system;
        specialArgs = {
          targetSystem = nixosConfigurations.nixos;
        };
        modules = [
          ./tools/iso.nix
        ];
      };
    };
    rpm = pkgs.callPackage ./tools/rpm.nix {
      inherit nixpkgs;
      qubesVersion = "4.2.0";
      nixosConfig = nixosConfigurations.nixos;
    };
    iso = nixosConfigurations.iso.config.system.build.isoImage;
  };
}
