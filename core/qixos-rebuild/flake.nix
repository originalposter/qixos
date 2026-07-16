{
  description = "qixos-rebuild";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    qixosCore.url = "path:..";
  };

  outputs = { nixpkgs, qixosCore, ... }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
    qubesAdmin = qixosCore.packages.${system}.qubes-core-admin-client;
  in {
    devShells.${system}.default = pkgs.mkShell {
      packages = [ pkgs.python3 pkgs.pyright pkgs.python3Packages.pydantic qubesAdmin ];
    };

    packages.${system} = let
      qixosPkgs = pkgs.callPackage ./. { qubes-core-admin-client = qubesAdmin; };
    in {
      default = qixosPkgs.qixosRebuild;
      switch = qixosPkgs.qixosSwitch;
    };
  };
}

