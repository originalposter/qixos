# Changelog

What changed in each release, newest first

## Unreleased

### Host ssh keys no longer stored in /etc/ssh
Fixed an issue where the default `host_*` ssh keys were stored in `/etc/ssh/`.

This meant that all appVMs shared the same host ssh keys.
This is especially problematic because `agenix` and `nix-sops` use the host to decrypt secrets from the nix store.

Turning this off, for anyone planting host keys from a secrets store instead, is
`services.qubes.sshHostKeys.enable = false`.
