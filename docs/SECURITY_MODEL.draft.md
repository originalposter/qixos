# Security model

What QixOS protects, what it does not, and how well we've established the difference.

**Status: public alpha. Nothing here has been tested against a running system.** Tags:
`[CODE]` read in QixOS source · `[ASSUMED]` relies on undocumented-to-us Qubes/Nix behaviour ·
`[UNVERIFIED]` believed, not established · `[TESTED]` — currently unused.

Invariants are normative: breaking one is a security bug. Each carries a *refute by* line; that is
the audit backlog and the basis for a useful testament.

## What QixOS bets on

1. The qrexec policy in `install.sh` is correctly scoped — protects your non-QixOS qubes.
2. The Nix build sandbox holds — protects your nubes from a config you installed. No defence in depth.
3. Your outer config's author is trustworthy — no mechanism, by design.
4. TLS to github and the maintainer's account, at install time.

## The QubesOS security model

QixOS piggy-backs heavily on QubesOS for security. The QubesOS security model is a basis for
thinking of security in QixOS which modifies it only very lightly and hesitantly.

The Qubes security model is based on virtual machines (VMs) which each is considered its own
security zone. A VM runs whatever software it wants inside of it and depending on that software and
the VM configuration, has a higher or lower risk of being 'compromised'. If the QubesOS security
model is sound the compromised VM can only compromise other VMs if those VMs are 'below' it in the
'security hierarchy'.

The 'security hierarchy' describes which VMs are 'above', 'below' or 'not related' to each other.
`dom0` is above all other VMs. A `TemplateVM` is above all `AppVM`s that use it as their template.
`AppVM`s are always not related, even if they share a template. A `TemplateVM` is not related to any
`AppVM` which does not depend on it. `StandaloneVM`s sit by themselves, not above or below any VM
except `dom0` — though if cloned from a compromised template they inherit that compromise.

There is a nuance called the qubes remote procedure call system (qrexec). This allows `dom0` to give
special permission for a specified VM to call a specified program in another specified VM,
regardless of where these VMs sit in the hierarchy. It is therefore critical that these policies are
constructed with care and that the programs which are opened up are especially hardened.

## QixOS additions to the hierarchy

`qixos-admin` is above every VM it creates and **not related** to everything else — a peer of your
other qubes, not a globally elevated VM. Scoping is by the `created-by-<admin>` tag, applied
automatically by dom0 on creation.

Two declarative artifacts have distinct security properties:

- **Outer configuration** — which nubes exist and their properties; each references its inner config
  by URL string. Evaluated in `qixos-admin` (`config.py:79–98`). Fully trusted: it is the root of a
  QixOS installation.
- **Inner configuration** — the NixOS config of one nube. Never evaluated in `qixos-admin`
  (Design decision 2). Evaluated and built on the TemplateVM. **Untrusted.**

## Invariants

**I-1. `qixos-admin` has no special privilege over any VM it did not create.**
`[UNVERIFIED]` Not "cannot interact with" — it has `sys-net` and can `qvm-copy` to a user-approved
target like any qube. Enforced by `/etc/qubes/policy.d/55-<admin>.policy` plus the
`<admin> @tag:created-by-<admin> allow target=dom0` line appended to `include/admin-local-rwx`
(`install.sh:44–99, 321–326`).
*Refute by*: finding a service in the `admin-local-rwx` expansion that takes effect on an untagged VM.

**I-2. `qixos-admin` cannot enlarge its own authority through tags.**
`[UNVERIFIED — suspected false]` Asserted at `install.sh:52–53` but established by no rule in the
policy file. Two directions, only one of which the comment addresses:
- Can another VM apply `created-by-<admin>`? — the claim as written.
- **Can `qixos-admin` apply _other_ tags to VMs it manages?** If `admin.vm.tag.Set` falls within
  `admin-local-rwx`, then yes — and any policy on your system keyed on `@tag:` becomes satisfiable
  by a QixOS VM. This would break I-1 and the "0-trust policy" claim at `install.sh:45–48`.
*Refute by*: confirming `admin.vm.tag.Set` reachability, then naming any tag-keyed policy in a
common Qubes install. **Highest-priority unknown in this document.**

**I-3. Compromise of an AppVM compromises no other VM.**
`[ASSUMED — Qubes]` Two by-design exceptions, both from Design decision 3:
- *Confidentiality*: siblings sharing a template read each other's full config from `/nix/store`
  (`make-nube-cluster.nix:11–15`).
- *Availability*: one AppVM's config can fail the template build or OOM it, denying service to the
  whole cluster (`protocol.py:56`; DESIGN.md "Known issues").

**I-4. Compromise of a TemplateVM compromises only AppVMs depending on it.**
`[ASSUMED — Qubes]` QixOS widens this: the generated flake forces every AppVM's `nixpkgs` to follow
the template's (`qixos_switch.py:171,177`), so the template also chooses all AppVM package
provenance.

**I-5. A malicious inner configuration compromises only the AppVM that uses it.**
`[CODE]` for the mechanism, `[ASSUMED]` for the sandbox. The template builds every dependent AppVM's
closure, but the template's activation script only `mkdir`s and `ln -sfn`s the result
(`bootstrap-template-linking.nix:10–18`); activation runs in the AppVM at boot
(`bootstrap-systemd-activation.nix:138–180`). **This invariant reduces entirely to Nix build sandbox
and pure-eval integrity.**
*Refute by*: sandbox escape · import-from-derivation · fixed-output derivations (network access
inside the sandbox) · pure-eval failing to block reads of template files, which would land them in
the store where every sibling reads them (see I-3) · a template config setting `sandbox = false`,
which QixOS neither forces nor warns about (`construct-qix-core-modules.nix` sets no `nix.settings`).

**I-6. `qixos.Switch` is write-only from `qixos-admin`'s perspective.**
`[CODE: qixos_switch.py:17–33; switch.py:84–133]` `qixos-rebuild` must not trust anything the
template returns beyond an exit code.
*Refute by*: any path where template-controlled bytes reach admin control flow. Template `stderr`
already reaches admin logs (`switch.py:126–131`) — log injection, not yet escalation.

**I-7. Parallel QixOS installations cannot control each other's VMs.**
`[UNVERIFIED]` Desideratum 7. If I-2 is false, admin A can tag its own VM `created-by-B`.
`management_tag` also comes from the outer config (`config.py:75`) with no evident constraint that
it match the installation's own tag.
*Refute by*: setting `managementTag` to another installation's tag and observing `get_managed_vms`.

**I-8. QixOS does not by default add vulnerable software to a VM.**
`[UNVERIFIED]` Hard to guarantee; the goal is to ship as little as possible. What QixOS adds to
every nube: the `qixos.Switch` qrexec endpoint on templates (`install.sh:99`,
`construct-qix-core-modules.nix:15–23`); two systemd activation jobs on AppVMs; and the repackaged
`qubes-pkgs`.
*Refute by*: a vulnerability in the above, or a `qubes-pkgs` derivation that drops a hardening
property present upstream.

## Not security boundaries

Listed so audit effort isn't spent here.

- **root vs. user inside a VM.** Inherited from Qubes, which permits the distinction but does not
  rely on it. A finding is not more severe for reaching root, and privilege separation inside a nube
  is not a QixOS security mechanism. `install.sh:101` states this for dom0. Where this document
  cites `user=root` or a root-run script, it is describing reach within an already-owned VM, not a
  crossed boundary.
- **`qixos-admin` → TemplateVM.** Admin owns its templates by design. Constructs that look alarming
  and are not, *given a trusted sender*: `tarfile.extractall(filter=reset_ownership)`
  (`qixos_switch.py:124`) replaces Python's `data` filter, so member paths are unchecked for `..`
  and absolute paths — arbitrary file write anywhere on the template; VM names and flake URLs
  interpolate into generated Nix unescaped (`qixos_switch.py:170–188`); VM names interpolate into
  the template's activation shell script (`bootstrap-template-linking.nix:13–16`).
  These stop being safe if a tarred directory contains attacker-chosen filenames — plausible, since
  Design decision 5 tars the user's entire git root.
- **TemplateVM → its own AppVMs.** Standard Qubes.

## Assumptions

1. **The Qubes security model holds.** A Xen escape is game-over; QixOS then guarantees nothing.
2. **The Nix build sandbox holds.** Equal billing with (1): I-5 has nothing behind it.

## Non-goals

1. Defending dom0, Xen, or the Qubes Admin API.
2. Defending against a malicious outer config.
3. Confidentiality of configuration between AppVMs sharing a template.
4. Availability within a cluster.
5. Protecting a user who disables the nix sandbox on a template.
6. Reproducibility as a security property.
7. Securing the software a user chooses to run in a nube. QixOS's concern is the attack surface
   QixOS itself adds.

## User obligations

1. Never put plaintext secrets in a nube config. Use `agenix`/`sops-nix`.
2. Treat an outer config as fully trusted code — copying one from the community repo hands its
   author your installation.
3. Do not disable the nix build sandbox on a template. Voids I-5.
4. Do not key your own qrexec policies on tags while running QixOS, until I-2 is resolved.
5. Prefer pinned flake refs to branch refs.

## Supply chain

`install.sh` runs in dom0 and installs nix via `curl | sh` (`:149`), installs the template RPM with
`--nogpgcheck` (`:214`), and fetches the admin flake from a mutable branch ref with
`--no-write-lock-file --refresh` (`:290`). No signature verification anywhere. The manual
("trustless") path in `install/INSTALL.md` is the higher-assurance option.

Inner configs are pinned only by the user's `flake.lock`; `--update` re-resolves mutable refs
(`qixos_switch.py:225–234`). A malicious upstream config reaches the template on next update,
contained by I-5.

## Community repository

Namespaced directories with rubber-stamped PRs is coherent **only** because of I-5: security does
not depend on review catching malware. This holds for *inner* configs. It does not hold for outer
configs, modules copied into a template config, or anything a user runs in `qixos-admin` — the repo
should distinguish these, and review effort belongs entirely on the latter.

## Attacker outcomes

| Attacker | Gains | Does not gain, if invariants hold |
|---|---|---|
| Malicious inner config | Sandboxed execution on the template; full control of its own AppVM; read of sibling configs; cluster DoS | Template root, sibling runtime, admin, other clusters, non-QixOS qubes |
| Compromised AppVM | Its own VM; whatever its `netvm` reaches | Template, siblings, admin |
| Compromised TemplateVM | Every AppVM in its cluster | Other clusters, admin, non-QixOS qubes |
| Compromised `qixos-admin` | Every QixOS VM | Non-QixOS qubes — conditional on I-1, I-2 |
| Malicious outer config | Same as compromised admin | Same condition |
| Network attacker on flake fetch | Same as malicious inner config; during install, admin-flake substitution | — |

## Changes requiring re-review

Update this document in the same change.

| Change | Invalidates |
|---|---|
| Policy strings in `install/install.sh` | I-1, I-2, I-7 |
| Granting `qixos-admin` any new Admin API | I-1, I-2 |
| Any use of `admin.vm.tag.Set` | I-2, I-7 |
| Parsing anything `qixos.Switch` returns | I-6 |
| Running AppVM-derived scripts on the template outside the sandbox | **I-5 — the core bet; don't** |
| Adding IFD, `--impure`, or `--no-sandbox` to the build path | I-5 |
| Setting `nix.settings` in core modules | I-5 |
| Evaluating any inner config in `qixos-admin` | I-5, Design decision 2 |
| Changing how `managementTag` is sourced | I-7 |
| Adding signatures or pinning to install | Supply chain — improves it, say so |

## Open questions

1. Does `include/admin-local-rwx` grant `admin.vm.tag.Set`? (I-2)
2. Should QixOS force `sandbox = true` on nube templates? (I-5)
3. Does flake pure-eval prevent an inner config reading template files? (I-5)
4. Can `managementTag` name another installation's tag? (I-7)
5. Should `qixos.Switch` untar with a path-checking filter as defence in depth?
6. Should VM names be charset-validated at the outer-config boundary?
