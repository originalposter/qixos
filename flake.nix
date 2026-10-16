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
    checks.${system} = {
      coreModulesEvaluate =
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

      # qixos.Switch builds a cluster's template before any of its AppVMs, and one AppVM
      # that fails must leave the template and its siblings standing. Both depend on the
      # template's closure not referring to an AppVM's, which the throw stands guard over.
      # Through mkNubeCluster, which is the call an older qixos.Switch still makes and so
      # the one place a template and its AppVMs are still handed over together.
      templateEvaluatesWithoutItsAppVms =
        let
          cluster = self.lib.mkNubeClusterWith { inherit nixpkgs; } {
            template.modules = [ ];
            apps.broken.modules = [ (throw "building the template evaluated an AppVM") ];
          };
        in
          builtins.seq
            cluster.nixosConfigurations.template.config.system.build.toplevel.drvPath
            (pkgs.runCommand "template-evaluates-without-its-appvms" { } "touch $out");
      # qrexec treats a service as TCP, qubes.ConnectTCP for one, only when its entry in
      # /etc/qubes-rpc is itself a link to /dev/tcp/<host>: it reads that one link and
      # checks the text, and otherwise stats the path, which /dev/tcp never resolves to.
      # So no such service may be reached through a second link. Failing on finding none
      # keeps a green result from meaning nothing was checked.
      qrexecTcpServicesAreDirectLinks =
        let
          nube = self.lib.mkNubeApp {
            directBuild = { inherit nixpkgs; };
            modules = [ ];
          };
          services = nube.nixosConfigurations.default.config.environment.etc."qubes-rpc".source;
        in
          pkgs.runCommand "qrexec-tcp-services-are-direct-links" { } ''
            found=0
            for entry in ${services}/*; do
              first=$(readlink "$entry") || continue
              case "$first" in
                /dev/tcp/*) found=$((found + 1)); continue ;;
              esac
              second=$(readlink "$first") || continue
              case "$second" in
                /dev/tcp/*)
                  echo "$(basename "$entry") reaches $second only through $first"
                  exit 1
                  ;;
              esac
            done
            if [ "$found" -eq 0 ]; then
              echo "no /dev/tcp service in ${services}"
              exit 1
            fi
            touch $out
          '';

      # install/build-nix-template is its own flake, and the installer builds it as
      # `?dir=install/build-nix-template#rpm`. It cannot be an input here: a `path:` input
      # copies only that subdirectory, so its `../../core/...` paths land outside the store
      # path and pure evaluation refuses them. Importing its flake.nix as a plain file
      # resolves those paths against this tree, where they belong.
      #
      # `self` is tied back to the outputs it returns, which is enough because that flake
      # reads only nixosModules and nixosProfiles off it, never outPath. It gets this
      # flake's nixpkgs rather than its own lock, so the check reports on one release.
      templateRpmEvaluates =
        let
          template = (import ./install/build-nix-template/flake.nix).outputs {
            self = template;
            inherit nixpkgs;
          };
        in
          builtins.seq
            template.rpm.drvPath
            (pkgs.runCommand "template-rpm-evaluates" { } "touch $out");
    };

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

    nixosModules.qubesModules = ./core/qubes-modules;

    nixosProfiles.basicQube = { ... }: {
      imports = [
        ./core/qubes-modules/basic-qube-profile.nix
      ];
    };

    # Base overlay should be included in all nubes
    overlays.base = import ./core/qubes-pkgs/overlay.nix;

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
