{ qixosCore }:
let
  # Releases core is checked against. `checks` in the flake evaluates the module set
  # against each, so this list is a claim someone verifies rather than a note.
  supportedNixpkgsReleases = [ "26.11" ];

  coreQixosModules = [
    qixosCore.nixosModules.qubesModules
    qixosCore.nixosProfiles.basicQube
    { nixpkgs.overlays = [ qixosCore.overlays.base ]; }
    ({ config, lib, pkgs, ... }:
    let
      # NOTE: The normal /etc/qubes-rpc path is *NOT* in the QREXEC_SERVICE_PATH variable.
      # If you want to create qubes remote execution (qrexec) endpoints they should be put in
      # `services.qubes.qrexec.packages` as packages.
      #
      # The below script is the script ran on all template VMs when `qixos-rebuild` pings them to switch
      # to a new flake. The qrexec call ought to be made to root (this is controlled in dom0 policy).
      qixosSwitchPackage = pkgs.runCommand "qixos-switch-package" {} ''
        mkdir -p $out/etc/qubes-rpc
        ln -s ${pkgs.qixos-switch}/bin/qixos-switch $out/etc/qubes-rpc/qixos.Switch
      '';
    in
    {
      # This qrexec endpoint is called by qixos-rebuild when switching
      # all of the templates.
      services.qubes.qrexec.packages = [ qixosSwitchPackage ];

      # I believe this should be set by us? I guess at least if we build the .iso?
      # or where should this value be specified? Should all config flakes define it?
      # Should it be defined in one place by the user and then linked into their config
      # by them? by us?
      # I suppose we could just allow them not to define it. They'll get a warning
      # and we could just tell them how they should do it. (with a basic template module imported
      # by basically all nubes)
      #
      # This value determines the NixOS release from which the default
      # settings for stateful data, like file locations and database versions
      # on your system were taken. It‘s perfectly fine and recommended to leave
      # this value at the release version of the first install of this system.
      # Before changing this value read the documentation for this option
      # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
      system.stateVersion = "26.05"; # Did you read the comment?

      # A nube picks its own nixpkgs and core's modules are evaluated against it, so the
      # versions core has been tried against are the ones it can stand behind. An option
      # that was renamed fails loudly on its own, but one whose default moved does not,
      # and refusing an untried release is the only thing that catches the second kind.
      assertions = [{
        assertion = config.services.qubes.core.allowUnsupportedNixpkgs
          || lib.elem lib.trivial.release supportedNixpkgsReleases;
        message =
          "qixos core supports nixpkgs ${lib.concatStringsSep ", " supportedNixpkgsReleases}"
          + " and this nube builds against ${lib.trivial.release}. Point the template's"
          + " nixpkgs at a supported release, add this one to"
          + " construct-qix-core-modules.nix once core has been checked against it, or set"
          + " services.qubes.core.allowUnsupportedNixpkgs to build anyway.";
      }];
    })
  ];
in
coreQixosModules
