# Copyright (c) 2024 eV Quirk
# Copyright (C) 2026 op (op@qixos.org)
# Derived from https://github.com/evq/qubes-nixos-template (MIT)
# SPDX-License-Identifier: GPL-2.0-or-later
{
  config,
  lib,
  pkgs,
  ...
}:
with lib; let
  pkg = config.services.qubes.core.package;

  # Met only on a qube dom0 has made a netvm (providesNetwork), which qubes-sysinit marks
  # before sysinit.target, so providesNetwork is the one switch. Read at boot: a nube given
  # providesNetwork while it runs serves nothing until it restarts.
  onNetvm = ["|/run/qubes/this-is-netvm" "|/run/qubes/this-is-proxyvm"];

  # A ruleset that flushes everything on load also clears the netvm's tables, which cannot
  # be restored without the downstreams reconnecting, so such a nube refuses to forward.
  nftablesFlushes = config.networking.nftables.enable && config.networking.nftables.flushRuleset;
  refuseForwarding = pkgs.writeShellScript "qubes-network-refuse" ''
    echo "not forwarding: networking.nftables.flushRuleset would clear this netvm's rules." >&2
    echo "set networking.nftables.flushRuleset = false and declare the ruleset with" >&2
    echo "networking.nftables.tables. NixOS turns it on for a raw ruleset, and for any" >&2
    echo "system.stateVersion before 23.11." >&2
    exit 1
  '';

  # The forwarding gate: drops everything arriving on a downstream interface (group 2, set
  # by vif-route-qubes) that would be forwarded. Without it a netvm forwards without the
  # firewall it is meant to have before its AppVM switch, while it still runs its
  # template's configuration and none of its own, and while the firewall daemon is down,
  # where stock Qubes keeps forwarding. ip_forward is no guard: other software may turn it
  # on. Opened by qixos-forwarding-gate below. Loading this file closes it from any state.
  gateClosed = pkgs.writeText "qixos-forwarding-gate-closed.nft" ''
    table inet qixos-forwarding-gate {
      chain forward {
        type filter hook forward priority filter - 10; policy accept;
      }
    }
    flush chain inet qixos-forwarding-gate forward
    add rule inet qixos-forwarding-gate forward iifgroup 2 counter drop
  '';
  # Also ends offloaded connections, which bypass the forward hook. vif-route-qubes adds
  # the flowtable back for the next downstream.
  closeGate = pkgs.writeShellScript "qixos-forwarding-gate-close" ''
    ${pkgs.nftables}/bin/nft -f ${gateClosed}
    ${pkgs.nftables}/bin/nft delete table inet qubes-nat-accel 2>/dev/null || true
  '';
in {
  options.services.qubes.networking = {
    enable = mkEnableOption "the qubes networking services";
  };

  config = mkIf config.services.qubes.networking.enable {
    services.qubes.core.enable = true;
    services.qubes.core.networking = true;

    services.resolved.enable = true;

    # qubes owns this file and nixos must not claim it. `setup-ip` writes the nameservers
    # from qubesdb into it at boot, deleting whatever symlink it finds there first, and
    # resolved reads them back out of it as its upstream servers. Declaring it here would
    # make every activation restore the symlink, which leaves resolved with no upstreams
    # at all: the qube keeps its addresses and its routes and resolves nothing.
    #
    # A reboot is what hides this. `setup-ip` runs after activation at boot, so it wins
    # there, and its unit is a oneshot that has already exited by the time anyone runs
    # `nixos-rebuild switch`. Nothing re-applies it afterwards.
    environment.etc."resolv.conf".enable = false;

    systemd.services.qubes-network-uplink = {
      # ensure the service is started on boot, since Install is ignored
      wantedBy = ["multi-user.target"];
      serviceConfig = {
        ExecStart = ["" "${pkg}/lib/qubes/init/network-uplink-wait.sh"];
      };
    };

    systemd.services."qubes-network-uplink@" = {
      # explicitly add qubes-db as a requirement, otherwise on upgrade they may be restarted
      # simultaneously which causes setup-ip to fail.
      requires = ["network-pre.target" "qubes-db.service"];
      # On a netvm setup-ip runs qubes-setup-dnat-to-ns, which execs nft.
      path = [pkgs.nftables];

      serviceConfig = {
        ExecStart = ["" "${pkg}/lib/qubes/setup-ip add \"%i\""];
        ExecStop = ["" "${pkg}/lib/qubes/setup-ip remove \"%i\""];
      };
    };

    # prevents renaming of xenlight net interfaces, to avoid race conditions
    systemd.network.links."80-qubes-vif" = {
      matchConfig.Driver = "vif";
      linkConfig.NamePolicy = "";
    };

    # ensure that dhcpcd doesn't conflict with the qubes network configuration
    networking.dhcpcd.enable = false;

    # The netvm side. The units are upstream's (make install-netvm); what is set here is
    # that they start, and where their commands are.

    systemd.services.qubes-antispoof = {
      wantedBy = ["multi-user.target"];
      # After a NixOS nftables ruleset loads at boot, which would otherwise clear it.
      after = ["nftables.service"];
      unitConfig.ConditionPathExists = onNetvm;
      serviceConfig.ExecStart = ["" "${pkgs.nftables}/bin/nft -f ${pkg}/etc/qubes/qubes-antispoof.nft"];
      # The gate starts closed, before xendriverdomain can bring up a downstream interface.
      serviceConfig.ExecStartPost = closeGate;
    };

    systemd.services.qubes-iptables = {
      wantedBy = ["multi-user.target"];
      # After a NixOS nftables ruleset loads at boot, which would otherwise clear it.
      after = ["nftables.service"];
      unitConfig.ConditionPathExists = onNetvm;
      path = [pkgs.nftables pkgs.qubes-core-qubesdb];
      serviceConfig.ExecStart = ["" "${pkg}/lib/qubes/init/qubes-iptables start"];
    };

    # Applies each downstream's qvm-firewall rules from qubesdb; without it they go
    # silently unenforced. conntrack: after applying rules the daemon drops connections
    # they no longer allow, and without conntrack it exits instead, deleting its rules.
    #
    # A VPN netvm's kill switch belongs in /rw/config/qubes-firewall-user-script or
    # /rw/config/qubes-firewall.d, as on stock Qubes: the daemon runs them before it
    # reports ready, so before forwarding starts.
    systemd.services.qubes-firewall = {
      wantedBy = ["multi-user.target"];
      path = [pkgs.conntrack-tools pkgs.nftables];
      serviceConfig.ExecStart = ["" "${pkg}/bin/qubes-firewall"];
    };

    # Turns forwarding on, bound to the firewall daemon: upstream only orders it after the
    # daemon, so stock Qubes keeps forwarding with no per-qube rules once the daemon exits.
    # Here a dead daemon stops forwarding until the next activation or reboot.
    #
    # Known issue: a daemon that exits on its own deletes its rules a moment, normally well
    # under a second, before systemd stops forwarding. Closing that would mean patching
    # upstream's daemon. Stopping it through systemd stops forwarding first.
    #
    # Requires anti-spoofing and the base rules, which upstream gets via network-pre.target.
    systemd.services.qubes-network = {
      wantedBy = ["multi-user.target"];
      bindsTo = ["qubes-firewall.service"];
      requires = ["qubes-antispoof.service" "qubes-iptables.service"];
      # Opens the gate whenever forwarding starts; see qixos-forwarding-gate.
      wants = ["qixos-forwarding-gate.service"];
      path = [pkgs.kmod pkgs.nftables pkgs.qubes-core-qubesdb];
      serviceConfig = {
        ExecStartPre = mkIf nftablesFlushes [refuseForwarding];
        ExecStart = ["" "${pkg}/lib/qubes/init/network-proxy-setup.sh"];
        ExecStop = ["" closeGate "${pkg}/lib/qubes/init/network-proxy-stop.sh"];
      };
    };

    # Opens the gate once forwarding is up and the nube runs its own configuration, after
    # the AppVM switch; a switch that fails leaves it closed. A unit of its own because
    # qubes-network cannot be ordered after the switch, which runs after default.target,
    # without a cycle.
    systemd.services.qixos-forwarding-gate = {
      description = "Open the netvm's forwarding gate";
      bindsTo = ["qubes-network.service"];
      requires = ["qixos-appvm-switch.service"];
      after = ["qubes-network.service" "qixos-appvm-switch.service"];
      unitConfig.ConditionPathExists = onNetvm;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${pkgs.nftables}/bin/nft flush chain inet qixos-forwarding-gate forward";
        ExecStop = closeGate;
      };
    };

    # A flushing ruleset removes the gate too, so it is declared there, closed.
    networking.nftables.tables = mkIf nftablesFlushes {
      qixos-forwarding-gate = {
        family = "inet";
        content = ''
          chain forward {
            type filter hook forward priority filter - 10; policy accept;
            iifgroup 2 counter drop
          }
        '';
      };
    };

    # `xl devd` is the backend for each downstream interface. Its hotplug script,
    # vif-route-qubes, adds the address to the anti-spoofing set, hence after it. Not
    # after forwarding: qrexec.nix orders the qrexec agent after this unit, and dom0 counts
    # the qube started once the agent connects.
    systemd.services.xendriverdomain = {
      wantedBy = ["multi-user.target"];
      # Required, so a missing set fails here rather than in each hotplug.
      requires = ["qubes-antispoof.service" "qubes-iptables.service"];
      after = ["qubes-antispoof.service" "qubes-iptables.service"];
      unitConfig.ConditionPathExists = onNetvm;
      path = [pkgs.conntrack-tools pkgs.iproute2 pkgs.nftables pkgs.qubes-core-qubesdb pkgs.util-linux];
    };

    # dom0 names the hotplug script `vif-route-qubes`, and libxl looks for it in
    # /etc/xen/scripts. It sources xen's vif-common.sh from its own directory, so both
    # packages' scripts go in the one directory.
    environment.etc."xen/scripts".source = pkgs.symlinkJoin {
      name = "xen-hotplug-scripts";
      paths = ["${pkgs.xen}/etc/xen/scripts" "${pkg}/etc/xen/scripts"];
    };
  };
}
