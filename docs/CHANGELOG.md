# Changelog

## v0.2.0

### Security
Three issues are fixed in this release.

- **AppVMs inherited their template's ssh host keys**. An AppVM's root volume is a fresh
  snapshot of its template's, so a host key written to the template's `/etc/ssh` was present
  in every nube of the cluster, and sshd used the key it found rather than generating one.
  Every nube answered ssh as the same machine and held every other nube's private host key.
  Any of them could impersonate the rest, and anything keyed to the host identity, `agenix`
  and `sops-nix` included, was decryptable across the cluster. The keys now live under
  `/rw/qixos/ssh` on the private volume, which is the only per-nube storage there is. See
  "Host ssh keys no longer stored in /etc/ssh".
- **qixos.Switch wrote output to qixos-admin**. `qixos-rebuild` inherited
  the switch's stdout and stderr, and the switch runs on a template evaluating configs qixos-admin
  does not trust. This was an unnecessary attack surface into the admin that has been closed.


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


### Core says which nixpkgs release it supports
A nube picks its own nixpkgs and core's modules are evaluated against it. Core names the
release it is built and checked against, 26.11, and refuses the rest at evaluation rather
than failing later in a way that is hard to attribute. An option core uses that was renamed
fails loudly on its own, but one whose default moved does not, and this is what catches the
second kind. To build against another release anyway, set
`services.qubes.core.allowUnsupportedNixpkgs = true` in the nube's config.


### nixpkgs 26.11
Core is built against nixpkgs 26.11, having been on 26.05.


### User units are no longer capped by the memory a nube booted with
A nube boots at its `memory` allocation and balloons up afterwards, but the kernel fixes
`threads-max` from the memory present at boot and systemd derives `DefaultTasksMax` from
that, neither recomputed. A nube that ended up with gigabytes still capped its user units
at a few hundred tasks, and a browser exceeds that across its content processes: thread
creation fails and the process dies. `DefaultTasksMax` is now unset.


### qixos.Switch tells the admin nothing but an exit status
A template evaluates and builds inner configs qixos does not trust, and qrexec connects a
service's stdout and stderr to the caller. Both are now closed, so a template cannot put
bytes of its choosing in front of the admin.

The switch logs to the template's journal and to `/var/qixos/switch.log` instead, and
`qixos-rebuild` prints that path on every switch.


### An out-of-memory kill during a switch is reported as one
Building a template's configuration is the largest thing that happens in a cluster, and a
template that runs out of memory takes the nix build with it rather than `nixos-rebuild`,
which then exits with an ordinary failure that says nothing about memory. The switch now asks
the kernel instead of reading the exit status: it compares the `oom_kill` counter in
`/proc/vmstat` from before the build, and reports an out-of-memory kill on that.

The build also raises its own `oom_score_adj` so the kernel prefers it to the switch
machinery around it, which is what lets the report be made at all rather than dying with it.


### Disposable nubes boot app-templates configuration
A disposable is named when it starts, so the switch job found no configuration under that
name, gave up, and left the qube running the template's system. It now looks itself up
under the nube it was disposed from.

There is no way to give a disposable a configuration distinct from its app-templates', and a
named disposable behaves no differently: its own name is never consulted.


### qrexec endpoints are served from /etc/qubes-rpc
Services were found through `QREXEC_SERVICE_PATH`, one store path per package, which left
`/etc/qubes-rpc` empty on every nube. They are now merged into the directory qrexec reads
by default, and two packages claiming one service name fail the build rather than
resolving by list order. `services.qubes.qrexec.packages` is unchanged.

`/etc/qubes/rpc-config` is now installed, having been missing entirely. It carries the
per-service settings qrexec reads beside a service, so nine services a nube already
implements change behaviour: `qubes.OpenInVM`, `qubes.StartApp`, `qubes.OpenURL`,
`qubes.SelectFile`, `qubes.SelectDirectory`, `qubes.ShowInTerminal` and
`qubes.InstallUpdatesGUI` now wait for the GUI session, and `qubes.ConnectTCP` and
`qubes.UpdatesProxy` no longer have a service descriptor written into their data.

`qubes.VMExecGUI` is restored. It was removed from the agent package along with
`qubes.VMExec`, which it symlinks to, and never recreated. Without it a GUI command run in
a disposable started before the session existed and found no `DISPLAY`.


### Removing nubes that name each other
Qubes refuses to remove a qube another one still points at, through `netvm` or
`defaultDispvm`. An apply removing both ends now retries until the order works out rather
than failing on whichever it reached first.

Removing only the qube being pointed at is refused before anything is deleted, since a
config that cannot be applied should not cost a qube on the way to saying so. Naming a
qube the qubes-wide default points at is reported separately, because the fix for that one
is in dom0 rather than in the config.


### systemd no longer breaks an ordering cycle while booting a nube
`qubes-rootfs-resize` was ordered after `qubes-qrexec-agent`, which put `local-fs.target`
behind units that run late in boot and closed a loop back through it. systemd resolves an
ordering cycle by deleting a job from the loop and booting anyway, so every boot dropped a
unit without failing, and which unit depended on where systemd entered the loop:
`local-fs.target` itself on some boots, `systemd-tmpfiles-setup`, `nss-user-lookup.target`,
`systemd-update-utmp` or `network.target` on others.

The ordering that unit actually needs is already declared in the unit qubes ships, so the
added edge is gone. Ordering is computed before conditions, so this cost a unit on AppVMs too,
where `qubes-rootfs-resize` never runs.


### Nubes keep the qubes nameservers across a switch
Nix and Qubes fought over control of `/etc/resolv.conf` which resulted in dns being broken in a nube
if it switched. Now Qubes alone owns `/etc/resolv.conf` and dns does not break on a switch.


### App nubes follow their template's qixCore
App nubes now use their templates nixpkgs and qixCore versions instead of having their own.
The exception is if the `directBuild` option is used.
This lets the template save on disk space by only building 1 version of packages.


### The user's default.target waits for a session
A nube started the user's `default.target` whether or not a graphical session existed, so
units that assume one failed at boot in a nube that has none. It starts when a session does.


### Home-manager no longer runs privileged
Home-manager carried a privileged status it does not need. Configurations follow the
de-privileged format.

Users are encouraged to use the nixos module for home-manager instead.


### Fixes
- Protocol error codes no longer exceed 255, so they survive a process exit. The
  out-of-memory report could not previously fire because its code arrived truncated.
- A nube created by an apply gets its properties on that same run rather than the next.
- A nube with two properties to change gets both. Only one was applied, and which one
  depended on field order.


### Nube disk sizes are declarative
A nube can now say how big its volumes should be, in a `volumes` block next to
`properties`:

```nix
volumes = {
  root = "20 GiB";
  private = "3 GiB";
};
```

`apply` grows a volume that is below the declared size. Sizes are floors, so a volume
already at or above one is left alone, and shrinking is not supported. `root` belongs to
templates and standalones; an AppVM's root is a snapshot of its template's, which qubes
will not resize.

Growing the volume of a running nube also grows the filesystem on it now. The
`qubes.ResizeDisk` endpoint dom0 calls to do that shipped with unresolved paths and
failed on any nube, leaving the growth stuck at the block device until the next boot.


### Host ssh keys no longer stored in /etc/ssh
Fixed an issue where the default `host_*` ssh keys were stored in `/etc/ssh/`.

This meant that all appVMs shared the same host ssh keys.
This is especially problematic because `agenix` and `nix-sops` use the host to decrypt secrets from the nix store.

Turning this off, for anyone planting host keys from a secrets store instead, is
`services.qubes.sshHostKeys.enable = false`.


### Project
QixOS has the GPL-2-or-later LICENSE.

The repository moved from codeberg.org to github.com.

Significant parts of the project are now being built with the help of LLMs.

The signing key's fingerprint is published so release tags can be verified.
