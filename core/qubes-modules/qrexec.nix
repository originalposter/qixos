# Copyright (c) 2024 eV Quirk
# Copyright (C) 2026 op (op@qixos.org)
# Derived from https://github.com/evq/qubes-nixos-template (MIT)
# SPDX-License-Identifier: GPL-2.0-or-later
{
  config,
  lib,
  pkgs,
  ...
}: let
  servicePackages =
    ["${pkgs.qubes-core-qrexec}" "${pkgs.qubes-core-agent-linux}"]
    ++ config.services.qubes.qrexec.packages;

  # Merged into the two directories qrexec reads by default rather than left as a search
  # path over store paths, so that /etc shows what the qube actually serves. Two packages
  # claiming one service name fail the build here instead of resolving by list order.
  qrexecEtc = pkgs.buildEnv {
    name = "qubes-rpc";
    paths = servicePackages;
    pathsToLink = ["/etc/qubes-rpc" "/etc/qubes/rpc-config"];
  };
in
  with lib; {
    options.services.qubes.qrexec = {
      enable = mkEnableOption "the qubes remote exec agent daemon";
      packages = mkOption {
        type = types.listOf types.path;
        default = [];
        description = ''
          List of packages containing {command}`qrexec` services.
          All files found in
          {file}`«pkg»/etc/qubes-rpc/`
          will be included, as will any per-service settings the package ships
          alongside them in {file}`«pkg»/etc/qubes/rpc-config/`.
        '';
        apply = map getBin;
      };
    };

    config = mkIf config.services.qubes.qrexec.enable {
      services.qubes.core.enable = true;

      boot.kernelModules = ["xen_evtchn" "xen_gntalloc"];

      # rpc-config carries the per-service settings qrexec reads next to a service:
      # `wait-for-session` for anything needing the GUI session up before it runs, and the
      # stream settings ConnectTCP and UpdatesProxy need to not have a service descriptor
      # written into their data.
      environment.etc."qubes-rpc".source = "${qrexecEtc}/etc/qubes-rpc";
      environment.etc."qubes/rpc-config".source = "${qrexecEtc}/etc/qubes/rpc-config";

      # adding to system packages will cause their xdg autostart files to be picked up
      environment.systemPackages = [
        pkgs.qubes-core-qrexec
      ];

      security.polkit.enable = true;
      security.pam.services.qrexec = {
        rootOK = true;
      };

      # TODO  just override parts of existing service?
      systemd.services.qubes-qrexec-agent = {
        description = "Qubes remote exec agent";
        requires = ["qubes-db.service"];
        wantedBy = ["multi-user.target"];
        after = ["systemd-modules-load.service" "xendriverdomain.service" "systemd-user-sessions.service"];
        environment = {
          QREXEC_SERVICE_PATH = "/etc/qubes-rpc";
          QREXEC_MULTIPLEXER_PATH = "${pkgs.qubes-core-qrexec}/lib/qubes/qubes-rpc-multiplexer";
        };

        serviceConfig = {
          Type = "notify";
          ExecStartPre = "${pkgs.coreutils}/bin/mkdir -p /var/log/qubes";
          ExecStart = "${pkgs.qubes-core-qrexec}/lib/qubes/qrexec-agent";
          KillMode = "process";
          # FIXME: Does SELinux makes sense here?
          SELinuxContext = "system_u:system_r:local_login_t:s0-s0:c0.c1023";
        };
      };
    };
  }
