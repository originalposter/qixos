# Copyright (c) 2024 eV Quirk
# Taken unmodified from https://github.com/evq/qubes-nixos-template (MIT)
# SPDX-License-Identifier: GPL-2.0-or-later
{
  config,
  lib,
  pkgs,
  ...
}:
with lib; {
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
        ExecStart = ["" "${config.services.qubes.core.package}/lib/qubes/init/network-uplink-wait.sh"];
      };
    };

    systemd.services."qubes-network-uplink@" = {
      # explicitly add qubes-db as a requirement, otherwise on upgrade they may be restarted
      # simultaneously which causes setup-ip to fail.
      requires = ["network-pre.target" "qubes-db.service"];

      serviceConfig = {
        ExecStart = ["" "${config.services.qubes.core.package}/lib/qubes/setup-ip add \"%i\""];
        ExecStop = ["" "${config.services.qubes.core.package}/lib/qubes/setup-ip remove \"%i\""];
      };
    };

    # prevents renaming of xenlight net interfaces, to avoid race conditions
    systemd.network.links."80-qubes-vif" = {
      matchConfig.Driver = "vif";
      linkConfig.NamePolicy = "";
    };

    # ensure that dhcpcd doesn't conflict with the qubes network configuration
    networking.dhcpcd.enable = false;
  };
}
