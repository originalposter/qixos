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
    qubesPackages = final: prev: {
      qubes-core-qubesdb = prev.callPackage ../../core/qubes-pkgs/qubes-core-qubesdb {};
      qubes-core-vchan-xen = prev.callPackage ../../core/qubes-pkgs/qubes-core-vchan-xen {};
      qubes-core-qrexec = prev.callPackage ../../core/qubes-pkgs/qubes-core-qrexec {};
      qubes-core-agent-linux = prev.callPackage ../../core/qubes-pkgs/qubes-core-agent-linux {};
      qubes-linux-utils = prev.callPackage ../../core/qubes-pkgs/qubes-linux-utils {};
      qubes-gui-common = prev.callPackage ../../core/qubes-pkgs/qubes-gui-common {};
      qubes-gui-agent-linux = prev.callPackage ../../core/qubes-pkgs/qubes-gui-agent-linux {};
      qubes-usb-proxy = prev.callPackage ../../core/qubes-pkgs/qubes-usb-proxy {};
    };

    pkgs = import nixpkgs {
      inherit system;
      overlays = [
        qubesPackages
      ];
    };
  in rec {
    overlays.default = qubesPackages;
    nixosModules.default = {
      config,
      lib,
      pkgs,
      ...
    }: {
      imports = [
        ../../core/qubes-modules/core.nix
        ../../core/qubes-modules/db.nix
        ../../core/qubes-modules/gui.nix
        ../../core/qubes-modules/networking.nix
        ../../core/qubes-modules/qrexec.nix
        ../../core/qubes-modules/updates.nix
        ../../core/qubes-modules/usb.nix
      ];
    };
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
