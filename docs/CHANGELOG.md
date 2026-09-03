# Changelog

What changed in each release, newest first

## Unreleased

### Nube properties
`memory`, `maxmem`, `vcpus`, `autostart`, `includeInBackups`, `qrexecTimeout`,
`shutdownTimeout` and `defaultDispvm` can now be set on a nube. `memory` was accepted and
silently ignored before, so a config declaring it did nothing.

A property qixos does not know is now an error rather than being dropped, which catches a
misspelling and a property from a newer qixos alike.

`defaultDispvm` must name a qube that exists or that the same config declares, and that
sets `templateForDispvms`. Standalone nubes are validated the same way as the rest, which
they were not before.

### netvm is left alone when a config says nothing about it
Omitting `netvm` used to put a qube back on the qubes default. It now leaves the qube as
it is, like every other property.

To ask for the default, say so: `netvm = "default"`. `netvm = "none"` still means no
network, and existing declarations of it are unaffected. The same three states work for
`defaultDispvm`.

### Core says which nixpkgs releases it supports
A nube picks its own nixpkgs and core's modules are evaluated against it. Core now names
the releases it has been checked against and refuses the rest, rather than failing later
in a way that is hard to attribute. To build against an untested release anyway, set
`services.qubes.core.allowUnsupportedNixpkgs = true` in the nube's config.

### User units are no longer capped by the memory a nube booted with
A nube boots at its `memory` allocation and balloons up afterwards, but the kernel fixes
`threads-max` from the memory present at boot and systemd derives `DefaultTasksMax` from
that, neither recomputed. A nube that ended up with gigabytes still capped its user units
at a few hundred tasks, and a browser exceeds that across its content processes: thread
creation fails and the process dies. `DefaultTasksMax` is now unset.

Nubes pick this up on their next boot, not on switch.

### qixos.Switch tells the admin nothing but an exit status
A template evaluates and builds inner configs qixos does not trust, and qrexec connects a
service's stdout and stderr to the caller. Both are now closed, so a template cannot put
bytes of its choosing in front of the admin.

The switch logs to the template's journal and to `/var/qixos/switch.log` instead, and
`qixos-rebuild` prints that path on every switch.

### Fixes
- Protocol error codes no longer exceed 255, so they survive a process exit. The
  out-of-memory report could not previously fire because its code arrived truncated.
- A nube created by an apply gets its properties on that same run rather than the next.
- A nube with two properties to change gets both. Only one was applied, and which one
  depended on field order.

### Host ssh keys no longer stored in /etc/ssh
Fixed an issue where the default `host_*` ssh keys were stored in `/etc/ssh/`.

This meant that all appVMs shared the same host ssh keys.
This is especially problematic because `agenix` and `nix-sops` use the host to decrypt secrets from the nix store.

Turning this off, for anyone planting host keys from a secrets store instead, is
`services.qubes.sshHostKeys.enable = false`.
