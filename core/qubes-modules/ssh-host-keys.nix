# Copyright (C) 2026 op (op@qixos.org)
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Gives each nube ssh host keys of its own, on its private volume.
#
# An AppVM's root volume is a fresh snapshot of its template's on every boot, so a host key
# in the template's /etc/ssh is in every AppVM of the cluster, and sshd uses a key it finds
# rather than generating one. The whole cluster then answers ssh as the same machine. The
# same snapshot is why a nube that does generate a key of its own loses it at the next
# boot. The private volume is the only per-nube storage that survives a boot, so the keys
# live there and /etc/ssh only points at them.
{
  config,
  lib,
  ...
}: let
  cfg = config.services.qubes.sshHostKeys;

  # nixpkgs' own defaults, moved. Changing which key types a nube offers is a separate
  # decision from where they are kept.
  keys = [
    {
      type = "rsa";
      bits = 4096;
      name = "ssh_host_rsa_key";
    }
    {
      type = "ed25519";
      name = "ssh_host_ed25519_key";
    }
  ];

  path = key: "${cfg.directory}/${key.name}";
in {
  options.services.qubes.sshHostKeys = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = config.services.openssh.enable;
      defaultText = lib.literalExpression "config.services.openssh.enable";
      description = ''
        Keep this nube's ssh host keys on its private volume, so that they are its own
        and survive a reboot. Turn this off if something else owns the host keys, such as
        a secrets tool planting them from an encrypted store.
      '';
    };

    directory = lib.mkOption {
      type = lib.types.str;
      default = "/rw/qixos/ssh";
      description = "Directory on the private volume holding this nube's host keys.";
    };
  };

  config = lib.mkIf cfg.enable {
    services.openssh.hostKeys =
      map (
        key:
          {
            inherit (key) type;
            path = path key;
          }
          // lib.optionalAttrs (key ? bits) {inherit (key) bits;}
      )
      keys;

    environment.etc = lib.listToAttrs (lib.concatMap (key: [
        (lib.nameValuePair "ssh/${key.name}" {source = path key;})
        (lib.nameValuePair "ssh/${key.name}.pub" {source = "${path key}.pub";})
      ])
      keys);

    # sshd-keygen creates the directory it is pointed at, so with /rw unmounted it would
    # generate the keys onto the root volume, which a template commits on shutdown and
    # every AppVM then inherits.
    systemd.services.sshd-keygen = lib.mkIf config.services.openssh.generateHostKeys {
      after = ["qubes-mount-dirs.service"];
      requires = ["qubes-mount-dirs.service"];
    };
  };
}
