{
  description = "example nixos templatevm configuration";

  inputs = {
    # Pinned. This is the flake an installed template rebuilds from, so an unpinned
    # input here means every install gets a different system, and core's default branch
    # rather than the release. No lock ships beside it: a lock names a rev of the commit
    # that contains it, and the tag below pins core on its own.
    qubes-nixos-template.url = "git+https://github.com/originalposter/qixos?ref=refs/tags/v0.2.0";

    # Core's nixpkgs, not one of our own. Core's modules are only checked against the
    # release it pins, so the template built from them should use that same nixpkgs.
    nixpkgs.follows = "qubes-nixos-template/nixpkgs";
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
