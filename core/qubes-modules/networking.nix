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

  # A condition met only on a qube dom0 has made a netvm, which qubes-sysinit marks
  # before sysinit.target (ProxyVM with a netvm of its own, NetVM without). Gating on it
  # at runtime, rather than on an inner-config option, keeps providesNetwork the one
  # switch and keeps these units out of the window where an AppVM still runs its
  # template's closure. Upstream starts qubes-antispoof and qubes-iptables on every
  # qube; gated here too, so a nube that serves nothing keeps the firewall it had.
  # Read at boot, so a nube given providesNetwork while it runs serves nothing until it
  # restarts.
  onNetvm = ["|/run/qubes/this-is-netvm" "|/run/qubes/this-is-proxyvm"];

  # A NixOS nftables ruleset that flushes everything on each load (a raw `ruleset` does
  # by default) also clears the netvm's tables: anti-spoofing, per-interface entries and
  # every downstream's rules. A netvm cannot recover from that without its downstreams
  # reconnecting, so such a nube refuses to forward at all.
  nftablesFlushes = config.networking.nftables.enable && config.networking.nftables.flushRuleset;
  refuseForwarding = pkgs.writeShellScript "qubes-network-refuse" ''
    echo "not forwarding: networking.nftables.flushRuleset would clear this netvm's rules." >&2
    echo "set networking.nftables.flushRuleset = false and declare the ruleset with" >&2
    echo "networking.nftables.tables. NixOS turns it on for a raw ruleset, and for any" >&2
    echo "system.stateVersion before 23.11." >&2
    exit 1
  '';

  # The forwarding gate. There are times a netvm would otherwise forward downstream
  # traffic without the firewall it is meant to have: most notably before the AppVM
  # switch, when it runs its template's configuration and none of its own (a VPN tunnel
  # and its kill switch, say), and whenever the firewall daemon is not running, since
  # its per-qube rules go with it. Stock Qubes forwards in that case: a dead daemon
  # leaves forwarding on with its rules gone. ip_forward cannot be relied on to stop
  # either, since other software on the nube may turn it on.
  #
  # So one rule drops everything that arrives on a downstream interface (vif-route-qubes
  # puts each in interface group 2) and would be routed on, in front of everything else
  # forwarding depends on. qixos-forwarding-gate below opens it once the firewall daemon
  # runs every downstream's rules and the nube runs its own configuration, and it closes
  # whenever either stops. Loading this file closes it, from whatever state; opening it
  # flushes the chain.
  gateClosed = pkgs.writeText "qixos-forwarding-gate-closed.nft" ''
    table inet qixos-forwarding-gate {
      chain forward {
        type filter hook forward priority filter - 10; policy accept;
      }
    }
    flush chain inet qixos-forwarding-gate forward
    add rule inet qixos-forwarding-gate forward iifgroup 2 counter drop
  '';
  # Closing also removes the flowtable vif-route-qubes offloads established connections
  # into, since an offloaded connection skips the forward hook the gate sits in. The next
  # downstream to come up adds it back.
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

    # The netvm side, for qubes that route others' traffic. Every unit below is upstream's,
    # installed by the package's `make install-netvm`; what is set here is that it starts
    # and where its commands are. Anti-spoofing and the base rules come first. Then the
    # firewall daemon and forwarding, and beside them the backend for the downstream
    # qubes' interfaces.

    systemd.services.qubes-antispoof = {
      wantedBy = ["multi-user.target"];
      # After a NixOS nftables ruleset loads at boot, which would otherwise clear it.
      after = ["nftables.service"];
      unitConfig.ConditionPathExists = onNetvm;
      serviceConfig.ExecStart = ["" "${pkgs.nftables}/bin/nft -f ${pkg}/etc/qubes/qubes-antispoof.nft"];
      # The forwarding gate starts closed, before xendriverdomain, which requires this
      # unit, can bring up any downstream interface.
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

    # Applies each downstream qube's firewall rules, which dom0 writes into this qube's
    # qubesdb. Without it every downstream qube's rules are silently ignored: dom0 shows
    # them as set, and nothing tells the qube they are not enforced. Gated by upstream on
    # the qubes-firewall service, which qubes-sysinit turns on for a netvm.
    #
    # conntrack because after applying a qube's rules the daemon drops that qube's now
    # disallowed connections. Without it that call raises OSError, which its watch loop
    # takes for a termination signal: it deletes every rule and exits. (It also tries to
    # notify the user of a failed rule through runuser, against a hardcoded /usr PATH
    # that has no notify-send on NixOS; the failure is in its journal regardless.)
    #
    # A VPN netvm's kill switch belongs in /rw/config/qubes-firewall-user-script or
    # /rw/config/qubes-firewall.d, as on stock Qubes: the daemon runs those before it
    # reports ready, and nothing is forwarded before then. /rw is there from the first
    # moment of boot, whichever configuration is running.
    systemd.services.qubes-firewall = {
      wantedBy = ["multi-user.target"];
      path = [pkgs.conntrack-tools pkgs.nftables];
      serviceConfig.ExecStart = ["" "${pkg}/bin/qubes-firewall"];
    };

    # Turns forwarding on. Gated by upstream on the qubes-network service, which
    # qubes-sysinit turns on for a netvm.
    #
    # bindsTo the firewall daemon, so forwarding runs only while the daemon does. The
    # daemon deletes its per-qube rules when it exits and the base rules under them
    # forward everything. Upstream only orders this unit after it, so on stock Qubes a
    # daemon that exits leaves every downstream forwarded with no rules. Here a netvm
    # whose daemon died serves nothing until the next activation or reboot starts both
    # again.
    #
    # Known issue: a daemon that exits on its own deletes its rules before systemd sees
    # it gone, so for that moment, normally well under a second, downstream traffic is
    # forwarded without them. Stopping it through systemd has no such gap, since upstream
    # orders it before this unit and forwarding stops first; a killed daemon never
    # deletes its rules. Closing it would mean patching upstream's daemon.
    #
    # requires anti-spoofing and the base rules too (upstream fails them via
    # network-pre.target), without which it would forward with no masquerade and let
    # downstreams spoof each other.
    systemd.services.qubes-network = {
      wantedBy = ["multi-user.target"];
      bindsTo = ["qubes-firewall.service"];
      requires = ["qubes-antispoof.service" "qubes-iptables.service"];
      # Every start of forwarding tries to open the gate; it waits for the nube's own
      # configuration, which this unit cannot be ordered after (see qixos-forwarding-gate).
      wants = ["qixos-forwarding-gate.service"];
      path = [pkgs.kmod pkgs.nftables pkgs.qubes-core-qubesdb];
      serviceConfig = {
        ExecStartPre = mkIf nftablesFlushes [refuseForwarding];
        ExecStart = ["" "${pkg}/lib/qubes/init/network-proxy-setup.sh"];
        ExecStop = ["" closeGate "${pkg}/lib/qubes/init/network-proxy-stop.sh"];
      };
    };

    # Opens the forwarding gate once forwarding is up and the nube runs its own
    # configuration. Until the AppVM switch, an AppVM runs its template's closure, which
    # carries the netvm side but none of the nube's own config, a VPN tunnel say. A switch
    # that fails, a missing build included, leaves the gate closed and the downstreams
    # with nothing. A standalone's switch succeeds at once; a template never gets here.
    #
    # A unit of its own because qubes-network cannot be ordered after the switch: the
    # switch runs after default.target, which is ordered after what multi-user.target
    # wants, qubes-network included. Bound to qubes-network, so it closes with it, and
    # pulled in by it, so it reopens when forwarding starts again; on a later activation
    # the switch is still active and it reopens at once.
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

    # A ruleset that flushes everything on load also removes the gate. Declared there too,
    # so each load puts it back closed; such a nube refuses to forward anyway.
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

    # `xl devd` (ExecStart from core.nix) is the backend for each downstream's interface,
    # running the hotplug script that brings one up and adds its address to the
    # anti-spoofing set, hence after that set exists. Not after forwarding: qrexec.nix
    # orders the qrexec agent after this unit and dom0 counts the qube started once the
    # agent connects, so waiting on the firewall daemon here would hold the qube's start
    # behind it, and nothing is forwarded before qubes-network anyway. The hotplug
    # script, vif-route-qubes, runs with this unit's PATH plus xen's own directories.
    systemd.services.xendriverdomain = {
      wantedBy = ["multi-user.target"];
      # Required, not only ordered, so a missing set fails here rather than in each
      # downstream's hotplug, where nothing reports it.
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
