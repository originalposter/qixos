{
  description = ''
  This flake represents the core parts of QixOS.
  '';

  inputs = {
    nixpkgs.url = "nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs, ... }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
    };
    corePkgs = import nixpkgs {
      inherit system;
      overlays = [ self.overlays.base ];
    };
    adminPkgs = import nixpkgs {
      inherit system;
      overlays = [ self.overlays.admin ];
    };
  in {
    lib = {
      mkNubeClusterWith = import ./core/qixos-nix-libs/make-nube-cluster.nix { qixosCore = self; };
      mkNubeTemplate = import ./core/qixos-nix-libs/make-nube-template.nix { qixosCore = self; };
      mkNubeApp = import ./core/qixos-nix-libs/make-nube-app.nix { qixosCore = self; };
      mkNubeStandalone = import ./core/qixos-nix-libs/make-nube-template.nix { qixosCore = self; };
    };

    # Core's modules are evaluated against whatever nixpkgs a nube pins, so the releases
    # construct-qix-core-modules.nix claims to support are checked here rather than
    # asserted and hoped for. Forcing drvPath evaluates the whole module system without
    # building any of it, which is where a renamed or removed option surfaces.
    checks.${system}.coreModulesEvaluate =
      let
        nube = self.lib.mkNubeApp {
          directBuild = { inherit nixpkgs; };
          modules = [ ];
        };
      in
        # seq forces the derivation to be instantiated, which evaluates the whole module
        # system, and then returns a derivation that does not reference it. Naming drvPath
        # in the env instead makes nix build the entire nube.
        builtins.seq
          nube.nixosConfigurations.default.config.system.build.toplevel.drvPath
          (pkgs.runCommand "core-modules-evaluate" { } "touch $out");

    # Everything needed to run the qixos-rebuild test suite and its linter by hand.
    # `nix develop -c pytest core/qixos-rebuild/tests -v` runs them against the working
    # tree, with no rebuild and no git step, which `nix build .#qixos-rebuild` needs.
    devShells.${system}.default = adminPkgs.mkShell {
      packages = [
        (adminPkgs.python3.withPackages (ps: [ ps.pytest ps.pydantic ps.flake8 ]))
        adminPkgs.qubes-core-admin-client

        (adminPkgs.writeShellScriptBin "run-unit-tests" ''
          root=$(${pkgs.git}/bin/git rev-parse --show-toplevel) || {
            echo "run-unit-tests: run this from inside the qixos checkout" >&2
            exit 1
          }
          exec pytest "$root/core/qixos-rebuild/tests" "$@"
        '')
      ];

      # qubes-core-admin-client is a plain mkDerivation rather than a buildPythonPackage,
      # so python3.withPackages cannot compose it and its site-packages has to be added
      # here. Inside a nix build the python setup hooks do this from propagatedBuildInputs.
      shellHook = ''
        root=$(${pkgs.git}/bin/git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
        export PYTHONPATH="$root/core/qixos-rebuild/src:${adminPkgs.qubes-core-admin-client}/${adminPkgs.python3.sitePackages}''${PYTHONPATH:+:$PYTHONPATH}"
      '';
    };

    packages.x86_64-linux = {
      inherit (corePkgs)
        qubes-gui-common
        qubes-core-vchan-xen
        qubes-core-qubesdb
        qubes-core-qrexec
        qubes-linux-utils
        qubes-core-agent-linux
        qubes-gui-agent-linux
        qixos-switch
        qubes-usb-proxy;

      inherit (adminPkgs)
        qixos-rebuild
        qubes-core-admin-client
        # This is kind of a hack to get the qubes admin `clone_vm` not error on qvm-appmenus missing
        qvm-appmenus-stub;
    };

    nixosModules.qubesModules = {...}: {
      imports = [
        ./core/qubes-modules/appmenus.nix
        ./core/qubes-modules/core.nix
        ./core/qubes-modules/db.nix
        ./core/qubes-modules/gui.nix
        ./core/qubes-modules/networking.nix
        ./core/qubes-modules/qrexec.nix
        ./core/qubes-modules/ssh-host-keys.nix
        ./core/qubes-modules/updates.nix
        ./core/qubes-modules/usb.nix
      ];
    };

    nixosProfiles.basicQube = { ... }: {
      imports = [
        ./core/qubes-modules/basic-qube-profile.nix
      ];
    };

    # Base overlay should be included in all nubes
    overlays.base = final: prev: {
      qubes-core-vchan-xen = final.callPackage ./core/qubes-pkgs/qubes-core-vchan-xen {};
      qubes-core-qubesdb = final.callPackage ./core/qubes-pkgs/qubes-core-qubesdb {};
      qubes-core-agent-linux = final.callPackage ./core/qubes-pkgs/qubes-core-agent-linux {};
      qubes-core-qrexec = final.callPackage ./core/qubes-pkgs/qubes-core-qrexec {};
      qubes-gui-agent-linux = final.callPackage ./core/qubes-pkgs/qubes-gui-agent-linux {};
      qubes-gui-common = final.callPackage ./core/qubes-pkgs/qubes-gui-common {};
      qubes-linux-utils = final.callPackage ./core/qubes-pkgs/qubes-linux-utils {};
      qubes-usb-proxy = final.callPackage ./core/qubes-pkgs/qubes-usb-proxy {};
      qixos-switch = (final.callPackage ./core/qixos-rebuild {}).qixosSwitch;
    };

    overlays.admin = nixpkgs.lib.composeManyExtensions [
      self.overlays.base
      (final: prev: {
        qubes-core-admin-client = final.callPackage ./core/qubes-pkgs/qubes-core-admin-client {};
        qixos-rebuild = (final.callPackage ./core/qixos-rebuild {}).qixosRebuild;
        qvm-appmenus-stub = pkgs.writeShellScriptBin "qvm-appmenus" ''
          exit 0
        '';
      })
    ];
  };
}
