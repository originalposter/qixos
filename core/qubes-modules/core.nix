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
  cfg = config.services.qubes.core;
in
  with lib; {
    options.services.qubes.core = {
      enable = mkEnableOption "the core qubes services";
      networking = mkEnableOption "include core qubes networking services";
      package = mkOption {
        type = types.package;
        description = "qubes-core-agent-linux package as configured by the qubes module options";
        internal = true;
      };
      allowUnsupportedNixpkgs = mkOption {
        type = types.bool;
        default = false;
        description = ''
          Build this nube against a nixpkgs release qixos core has not been checked
          against. The check exists because an option core uses may have been renamed,
          which fails loudly, or had its default changed, which does not.
        '';
      };
      username = mkOption {
        type = types.str;
        description = "the username of the primary account";
        default = "user";
      };
    };
    config = mkIf cfg.enable (
      let
        qubes-core-agent-linux =
          if cfg.networking
          then (pkgs.qubes-core-agent-linux.override {enableNetworking = true;})
          else pkgs.qubes-core-agent-linux;
      in {
        services.qubes.core.package = qubes-core-agent-linux;
        services.qubes.db.enable = true;

        users.groups = {
          qubes = {
            # supposedly this should be 98, however 995 matches the debian value
            gid = 995;
          };
          "${cfg.username}" = {
            gid = 1000;
          };
        };
        # We don't need to set shell as defaulting to bash here because nixos already does that
        users.users.${cfg.username} = {
          createHome = true;
          group = "${cfg.username}";
          extraGroups = ["qubes" "wheel"];
          home = "/home/${cfg.username}";
          isNormalUser = true;
          # Passwordless default on qubes
          password = lib.mkDefault "";
          uid = 1000;
        };
        security.sudo.wheelNeedsPassword = false;
        security.pam.services.su.text = lib.mkDefault (lib.mkBefore ''
          auth sufficient ${pkgs.linux-pam}/lib/security/pam_succeed_if.so use_uid user ingroup qubes
        '');
        # ensure qvm-console-dispvm is logged in
        services.getty.autologinUser = "${cfg.username}";

        fileSystems = {
          "/" = {
            device = "/dev/mapper/dmroot";
            fsType = "ext4";
          };
          "/proc/xen" = {
            device = "xen";
            fsType = "xenfs";
            noCheck = true;
            options = [ "nofail" ];
          };
          "/rw" = {
            device = "/dev/xvdb";
            fsType = "auto";
            options = [
              "noauto"
              "defaults"
              "discard"
              "nosuid"
              "nodev"
            ];
          };
          "/home" = {
            depends = ["/rw"];
            device = "/rw/home";
            fsType = "none";
            options = [
              "noauto"
              "bind"
              "defaults"
              "nosuid"
              "nodev"
            ];
          };
          "/usr/local" = {
            depends = ["/rw"];
            device = "/rw/usrlocal";
            fsType = "none";
            options = [
              "noauto"
              "bind"
              "defaults"
            ];
          };
        };
        systemd.tmpfiles.rules = [
          # create mount point
          "d /rw 0755 root root"
          # create mount point
          "d /usr/local 0755 root root"
          # mkdir so that first-boot-completed can be created here
          "d /var/lib/qubes 0755 root root"
        ];
        swapDevices = [
          {
            device = "/dev/xvdc1";
          }
        ];

        # qfile-unpacker needs setuid otherwise it fails during initgroups
        security.wrappers.qfile-unpacker = {
          owner = "root";
          group = "root";
          source = "${qubes-core-agent-linux}/bin/qfile-unpacker";
          setuid = true;
        };

        # adding to system packages will cause their xdg autostart files to be picked up
        environment.systemPackages = [
          qubes-core-agent-linux
        ];
        services.udev.packages = [
          pkgs.qubes-linux-utils
          qubes-core-agent-linux
        ];
        systemd.packages = [
          pkgs.qubes-linux-utils
          qubes-core-agent-linux
        ];

        # on other distros this is added on install of the package,
        # rather than create another module we just include in core
        systemd.services.qubes-meminfo-writer = {
          # ensure the service is started on boot, since Install is ignored
          wantedBy = ["multi-user.target"];

          serviceConfig = {
            ExecStart = ["" "${pkgs.qubes-linux-utils}/bin/meminfo-writer 30000 100000 /run/meminfo-writer.pid"];
          };
        };

        systemd.services.qubes-early-vm-config = {
          # ensure the service is started on boot, since Install is ignored
          wantedBy = ["sysinit.target"];

          serviceConfig = {
            ExecStart = ["" "${qubes-core-agent-linux}/lib/qubes/init/qubes-early-vm-config.sh"];
          };
        };

        systemd.services.qubes-misc-post = {
          # ensure the service is started on boot, since Install is ignored
          wantedBy = ["multi-user.target"];

          serviceConfig = {
            ExecStart = ["" "${qubes-core-agent-linux}/lib/qubes/init/misc-post.sh"];
          };
        };

        systemd.services.qubes-mount-dirs = {
          # ensure the service is started on boot, since Install is ignored
          wantedBy = ["multi-user.target"];

          serviceConfig = {
            ExecStart = ["" "${qubes-core-agent-linux}/lib/qubes/init/mount-dirs.sh"];
          };
        };

        systemd.services.qubes-rootfs-resize = {
          # ensure the service is started on boot, since Install is ignored
          wantedBy = ["multi-user.target"];
          # Seems like deadlock happens if we don't explicitly run after these.
          after = ["qubes-qrexec-agent.service" "qubes-sysinit.service"];
          unitConfig = {
            Before = "";
            # Running this on an AppVM makes it hang on startup
            # FIXME: This might not be true anymore if we have proper after conditions
            # FIXME: We actually want this to run for standalones too but right now it causes a systemd deadlock bug that breaks subtly.
            # For now we make this a template-only thing.
            # ConditionPathExists = "/run/qubes/persistent-full";
            ConditionPathExists = "/run/qubes/this-is-templatevm";
          };

          serviceConfig = {
            ExecStart = ["" "${qubes-core-agent-linux}/lib/qubes/init/resize-rootfs-if-needed.sh"];
            # There are reports that this job can sometimes take about 3 minutes
            TimeoutStartSec = 300;
          };
        };

        #systemd.services.qubes-sync-time = {
        # TODO how to setup the timer?

        systemd.services.qubes-sysinit = {
          # ensure the service is started on boot, since Install is ignored
          wantedBy = ["sysinit.target"];

          serviceConfig = {
            ExecStart = ["" "${qubes-core-agent-linux}/lib/qubes/init/qubes-sysinit.sh"];
          };
        };

        systemd.sockets."qubes-updates-proxy-forwarder" = {
          # ensure the socket is activated, since Install is ignored
          wantedBy = ["multi-user.target"];
        };

        systemd.services."qubes-updates-proxy-forwarder@" = {
          serviceConfig = {
            ExecStart = ["" "${pkgs.qubes-core-qrexec}/bin/qrexec-client-vm --use-stdin-socket '' qubes.UpdatesProxy"];
          };
        };

        systemd.services.xendriverdomain = {
          serviceConfig = {
            ExecStartPre = "${pkgs.coreutils}/bin/mkdir -p /var/log/xen";
            # Note: the first "" overrides the ExecStart from the upstream unit
            ExecStart = ["" "${pkgs.xen}/bin/xl devd"];
          };
        };

        # since there is no global nix proxy setting, add aliases which will
        # inherit the proxy settings from nix-daemon set by update-proxy-configs
        environment.interactiveShellInit = ''
          __nix_with_proxy() {
            local p
            p=$(systemctl show nix-daemon -p Environment \
                | grep -oP '(?<=all_proxy=)[^ ]*')
            all_proxy=$p https_proxy=$p "$@"
          }
          alias nix='__nix_with_proxy nix'
          alias nix-shell='__nix_with_proxy nix-shell'
          alias nixos-rebuild='__nix_with_proxy nixos-rebuild'
        '';
      }
    );
  }
