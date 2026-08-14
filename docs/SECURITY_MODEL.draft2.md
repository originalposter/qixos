# Space, time, data: working draft 2

Second pass. The first draft (`SECURITY_MODEL.draft.md`) is a list of invariants; this is the
frame they should hang off. Both kept for now so they can be diffed.

**Naming**: *outer configuration* → **admin config**. *inner configuration* → **nube config**.
The admin config is by definition what `qixos-admin` evaluates, so its trust level follows from
its name.

**Status marks**: `[NOW]` describes the system as it stands · `[PROPOSED]` a design not yet built ·
`[ASSUMED]` rests on Qubes or Nix behaviour we have not verified.

Everything below assumes no Xen escape. That assumption is not repeated per row; if it fails,
QixOS guarantees nothing.

## Two axes

Qubes provides **spatial** security domains: `qixos-admin`, a cluster's TemplateVM, each AppVM
nube, each DispVM. Nix provides **temporal** ones: eval time, build time, activation time,
application runtime.

Neither axis alone describes a security property. A property belongs to the pair, a *space-time
point*. Nube config evaluation is dangerous or harmless depending entirely on which domain it
happens in, and the same domain is trusted or not depending on which phase it is in.

The defence at each point is a Nix mechanism nested inside a Qubes mechanism: the eval sandbox
inside `qixos-admin`, the build sandbox inside a TemplateVM, and at application runtime, Xen
inside nothing.

## The map

| Point | Who acts here | Defence | Gains on success |
|---|---|---|---|
| `qixos-admin` · eval | admin config author (you) | nix eval sandbox, inside the most trusted domain | everything QixOS manages |
| `qixos-admin` · runtime | you, via `qixos-rebuild` | holds no nube configs `[PROPOSED]`; reads nothing back from a template but an exit code | everything QixOS manages |
| system-dev · runtime `[PROPOSED]` | you | none, it is your workstation | authorship of every local nube config |
| git-server AppVM · runtime `[PROPOSED]` | you, pushing from system-dev | serves one repo; speaks only to `qixos-admin` | every nube config on that server |
| git-server DispVM · runtime `[PROPOSED]` | whoever compromised the template pulling from it | disposable; carries one repo only | that repo; nothing survives shutdown |
| TemplateVM · update | nube config author, via flake inputs | `flake.lock` | choice of what gets built next |
| TemplateVM · eval | nube config author, and nobody else | nix pure-eval `[ASSUMED]` | reads of template state, if pure-eval leaks |
| TemplateVM · build | nube config author **and every build script in the closure** | nix build sandbox `[ASSUMED]` | on escape: the template, therefore the cluster, permanently |
| TemplateVM · activation | template config author (you) | near-empty by design | the cluster |
| AppVM nube · activation | nube config author | none, this is where they are meant to run | the nube |
| AppVM nube · runtime | the programs the nube config chose | Qubes isolation | the nube and the data in it, permanently |
| DispVM nube · runtime | the programs the nube config chose | Qubes isolation, plus nothing persists | the data in it, for as long as it runs |

The eval and build rows differ in a way that is easy to miss. At eval time the only actor is the
nube config author. At build time every build script in the closure runs too, which is a far
larger set of people and the reason the build sandbox carries more weight than any other single
mechanism here.

## The point kept empty

**A nube config never enters `qixos-admin`.** Not evaluated there, not built there, and
`[PROPOSED]` not even stored there. Nube configs sit at a lower trust level than the admin domain,
so keeping them out is what makes `qixos-admin` runtime safe. That is the entire reason dedicated
git-server nubes exist; without that requirement they would be unnecessary.

`[NOW]` the admin domain does hold local nube configs and tars them for transport. That is the gap
the git-server design closes.

Keeping a point empty is a stronger guarantee than defending one.

## Edges

Points are connected by qrexec calls, and the edges are where the shape of the map breaks.

| Edge | Carries | Direction of trust |
|---|---|---|
| `qixos-admin` → TemplateVM (`qixos.Switch`) | config tarball in, exit code out | admin parses the exit code and nothing else |
| TemplateVM → git-server DispVM `[PROPOSED]` | git fetch of one repo | template may read; DispVM learns nothing |
| system-dev → git-server AppVM `[PROPOSED]` | git push | authorship |
| `qixos-admin` → `dom0` (Admin API) | VM lifecycle calls | scoped by the `created-by-<admin>` tag |

## Cones, and where they fail

A useful simplification: **compromise travels forward in time and downward in space.** Own a
point and you own what comes after it and beneath it, nothing earlier and nothing above. Each
mechanism is then responsible for one thing: containing its attacker inside that cone.

The simplification is not true, and it fails in two ways.

**Edges break direction.** Every row above is a channel that crosses the hierarchy; that is what
qrexec is for. The list is short, which is the point of writing it down.

**Cones do not terminate, in a template.** Whoever owns a TemplateVM owns all of its root
filesystem, including `nixos-rebuild` and the `qixos.Switch` endpoint itself. They can leave those
hostile, so every future rebuild is performed by code the attacker controls. A rebuild does not
clean a template; nothing short of replacing it does. The declarative surface invites the opposite
assumption, that a template fully described by config is restored by re-deriving it.

**Assume the same of an AppVM nube.** There is an argument that a nube should recover: it does not
configure itself, the template builds and links its toplevel, so the activation it performs at boot
comes from outside it. The argument does not survive `/rw`. A nube that bind-mounts enough of its
own state can carry a compromise across a restart, and we do not want a security property that
depends on a user not having done that. Treat a compromised nube as compromised permanently.

A DispVM is the only domain where this is not so.

**Recovery is a by-product, not a goal.** We do not design against it, but nothing here promises
it. In the template case recovery depends on the build sandbox having held in the first place.

## Persistence as a choice

The three runtime domains trade differently, and a nube can be any of them.

- **AppVM nube**: holds your data and protects other nubes, but not against persistence within
  itself. A compromise here is permanent, as in a template.
- **DispVM nube**: holds your data, protects other nubes, and protects against persistence, at
  the cost of persistence. Nothing an attacker leaves survives; neither does anything you leave.
- **TemplateVM**: persistence is total and unrecoverable.

## Configs

Three kinds, with different owners and different consequences.

**Admin config.** Which nubes exist, their properties, their cluster membership. Evaluated in
`qixos-admin`. Fully trusted: it is the root of an installation, and there is no mechanism
defending against a hostile one, by design. You author it, or you pull it from a remote repo, in
which case that repo's owner is trusted by you.

**Nube config.** The NixOS configuration of one nube. Evaluated and built on the TemplateVM,
never in `qixos-admin`. Untrusted. Its owner is either a remote git repo, or you via system-dev
and a local git-server nube. **Different nubes can have different owners at different trust
levels**, and that is the intended way to use the system.

**Template config.** A third kind by function, not by trust. It should be an empty shell; the
template rarely needs to do anything at activation. Use the standard minimal template, or one
like it. It is owned by whoever owns the admin config, because its author sits above every nube
in the cluster with no shield in between. Copying a community module into a template config is a
different act from adopting a nube config, and promotes its author to owner of the whole cluster.

### Where local nube configs live `[PROPOSED]`

You edit configs in **system-dev** and push them to a **git-server nube**, one repo per nube.
When a TemplateVM needs to pull, the git-server nube is served from a **DispVM**: the persistent
lock stays in the AppVM, the network-facing git server exists only in a copy that is destroyed
afterwards, and a template that compromises it learns only the one repo it was already entitled to
read. Compromising the git-server AppVM itself gives control of every nube config it serves, which
is why it serves one.

`qixos-admin` talks only to the AppVM. TemplateVMs talk only to the DispVM.

## Data and programs

Data has value. Programs have risk. They must be paired, because processing data means running
programs on it. Every partitioning decision in this document is an attempt to keep the amount of
value sitting next to a given amount of risk small; it cannot be brought to zero.

- **Data belongs in AppVM nubes.** That is what they are for.
- **Configs live everywhere.** They are not data; they describe where programs go.
- **The nube config chooses the programs. You choose the data.** Your usage decides what ends up
  in a nube; its config decides what runs there.

This bounds what QixOS can do for you. It cannot make a program safe. It can only let you choose
which programs you trust with which data, and then keep that choice from spilling into choices you
made elsewhere.

The consequence for I-5: "a malicious nube config compromises only the AppVM that uses it" is
containment that bounds nothing you care about, because that AppVM is where your data is. The
exotic path is a sandbox escape. The boring path is the config author adding a program, which
needs no vulnerability and is indistinguishable from the config working as intended.

## The trust ladder

You run nube A from Alice. Nube B, from Bob, shares your template.

| Their position | What you must trust them not to do |
|---|---|
| Author of your nube's config (Alice) | be malicious at all; she picks the programs that touch your data |
| Authors of the programs Alice selected | be malicious at all; they are the ones that actually touch it |
| Author of a config sharing your template (Bob), and every build script in his closure | possess *and* use a nix build sandbox escape |
| Author of a config in another cluster | possess *and* use a Xen escape |

A nix build sandbox escape is a serious vulnerability in a core Nix component, not a
misconfiguration. Requiring one of Bob is a real reduction in what you are trusting him with. A
Xen escape is assumed absent throughout, so the bottom rung is as good as the model gets.

Trusting a nube config author is more reasonable than trusting the authors of the programs they
select: a config is small, readable, attributable, and chosen deliberately, while the software it
pulls in is none of those. But the two are not equally filtered, and at build time the ordering
reverses.

### Review is the third variable

Build scripts arrive with review already attached. For an alacritty build script to reach a
template's sandbox with an escape in it, someone must write a malicious build script, get it past
the project's own reviewers, get it past nixpkgs reviewers, and hold a zero-day that works with no
network and no obvious trigger. A bug in alacritty is not that chain, and the chain is long.

A nube config arrives with no review attached. Nothing in nixpkgs looks at it. The author still
needs the same zero-day, still without network, and still has to land it on a git branch you
actually use, but they stand one unreviewed step from the sandbox rather than four reviewed ones.
At build time the nube config author is the larger risk of the two, which is the reverse of the
runtime ordering above.

That difference is review, not architecture, which names a variable the rest of this document does
not: **how much review a source has already had, and how much it needs to reach the trust level
you are about to extend it.** Nube configs can be reviewed too; that review simply sits somewhere
other than nixpkgs, and even a little of it goes a long way against a chain that already requires
a zero-day.

Formally, running nube A requires: Alice is not malicious, **and** not (Bob is malicious and Bob
has a sandbox escape), **and** no Xen escape exists.

You do not have to trust that the system resists every escape, only the ones reachable from a
config you actually use. Scoping, rather than review quality, is what makes a community repository
workable at all, though a little review improves matters a great deal and the repository should
still do it.

The scope is wider than it looks. Bob is inside it. You did choose Bob, but you chose him for a
different nube, and nothing about that decision was a decision about nube A.

## Isolation by instance

Moving Bob down a rung means putting him in another template cluster. The isolation itself is
Qubes'; the price you pay is a duplicated `/nix/store`.

The same move appears twice, and it is the general pattern: **the unit of isolation is an
instance, not a config.** Two git-server nubes run identical configs and differ only in which repo
they hold. Two template clusters run identical configs and differ only in which nube closures they
build. You partition by instantiating again with different data, and you pay in storage.

## Open

1. Is `update` a distinct temporal phase, or eval with network?
2. How much a compromised AppVM nube can actually persist through `/rw` is not established. The
   document assumes the worst deliberately and claims nothing that depends on the answer, so this
   is worth knowing but nothing rests on it.
3. Everything marked `[PROPOSED]` is a design, not a system. The `[NOW]` gap, admin holding and
   tarring local nube configs, is real until it is built.
