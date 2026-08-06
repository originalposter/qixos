# Overview
The core qixos codebase is divided up into roughly 3 domains:
- `qixos-rebuild` - python cli for deployment.
- `qixos-nix-libs` - nix libraries for making the various configurations.
- `qubes-modules` and `qubes-pkgs` - nix code for packaging qubes tooling to make nixos work on qubes.

Note that we refer to a QixOS VM as a 'nube' deriving from 'nix qube'

## qixos-rebuild
`qixos-rebuild` is the main cli entrypoint for turning your Qubes system into one conformant with a Nix config.
It runs inside of the `qixos-admin` VM and requires higher qrexec privileges set in dom0.
The rough responsibilities of `qixos-rebuild` is to
1) create, delete and update properties of VMs based on the outer qixos configuration.
2) coordinate with `qixos.Switch` in order to setup the internals of the VMs.

## qixos.Switch
`qixos.Switch` is a python script running on template VMs and standalone VMs.
It is called via qrexec by `qixos-rebuild` and its responsibilities are
1) coordinate over the `qixos.Switch` protocol with `qixos-rebuild`.
2) receive copies of locally defined configurations from `qixos-admin` and place in `/var/qixos/current-flake/local-repos/`
3) generate a flake at `/var/qixos/current-flake/flake.nix`
4) switches the template or standalone with `nixos-rebuild boot --flake /var/qixos/current-flake/flake.nix#template`

### Generated flake
The generated flake is the canonical declarative state of the template and standalone.
The flake pulls in the inner configuration flake for all AppVMs as well as the TemplateVMs own configuration.
It puts these together using the qixos nix library function `mkNubeCluster`.
This is responsible for hooking up the logic which later switches each AppVM to its own configuration on boot.

## Inner and outer configurations
There are two types of configurations
1) inner configurations - thin wrappers around regular `nixosSystem` configurations. Created through qixos nix functions `mkNubeApp`, `mkNubeTemplate`, and `mkNubeStandalone`.
Exposed as a `flake.nix` in the `qixosAppConfigurations`, `qixosTemplateConfigurations`, and `qixosStandaloneConfigurations` outputs.
This flake can be hosted both on a remote git server as well as locally on the `qixos-admin` VM.
2) outer configurations - declares several VMs and their properties, each VM references a string containing a url pointing to it's inner configurations flake.

The outer configuration is evaluated inside `qixos-admin` the inner configuration is never evaluated or built inside of `qixos-admin`.
This is in-line with desiderata 3.

## QixOS AppVM Switch systemd job
Each AppVM has it's own complete nixos configuration which is built and then symlinked in `/run/qixos/activation/<VM name>/nixos` by the TemplateVM.
The AppVM will on boot run a systemd job called `qixos-appvm-switch.service` which looks up the configuration for that AppVMs name and switches to it with `nixos-rebuild test --flake /run/qixos/activation/<VM name>/nixos`.
This will set up the AppVMs configuration.

## Isolation between QixOS systems and the Qubes system
The qixos admin VM is isolated from the rest of the Qubes system in the same way normal Qubes are isolated from each other.
This means you can install QixOS without compromising your larger Qubes system, you can mix and match qubes and nubes.

The installation allows for multiple qixos admin VMs to be installed in parallel, each admin controls the nubes that they create.
This is managed through a qubes concept called `tags`. A qubes VM can have a set of tags, and each qube automatically gets a tag upon creation called
`created-by-<name of creating VM>`.
QixOS uses this concept and creates a policy in dom0's `/etc/qubes/policy.d/` which lets each admin VM create new qubes and manage the qubes with the tag signifying that they were created by that admin.
Manage here essentially implies total control over such qubes. For the detail go and look at the policy in the installation script.

# Desiderata
Desiderata 1: We want to allow configuring QubesOS with the `nix` programming language to the largest extent possible

Desiderata 2: We want to maintain a very high level of security, ideally having at least as high security as QubesOS.

Desiderata 3: Users should be able to install an untrusted inner config and that ought only risk compromise of the VM installing that inner config. In other words installing a malicious AppVM should not compromise other parts of the system.

Desiderata 4: QixOS should be highly testable, both the core code and also the specific VMs configurations should expose a useful testing interface.

Desiderata 5: Rebuilding the system should be as fast as possible. What can be parallelized should be, what can be cached should be.

Desiderata 6: QixOS should be as convenient and ergonomic as possible. It should ideally be possible to have a AppVM configure itself without having to communicate with the admin VM.

Desiderata 7: It should be possible to have multiple isolated QixOS "clusters" running in parallel. For example one qixos system for testing and staging and the other the "real" one used by the user in normal situations.

Desiderata 8: QixOS should try to make using LLM agents as easy and secure as possible. QixOS is well suited for the use of LLM agents since it offers strong security through isolation as well as configuration as code (suitable to language models).
We should keep this in mind when designing.

Desiderata 9: QixOS should have clear error messages and codes.

Desiderata 10: QixOS should be an extension of QubesOS and should not require that a user could not use their QubesOS system in a normal manner in parallel.

# Architecture decisions
## Design decision 1
We've created a distinction between "outer configurations" and "inner configurations" where the outer is refering to the configuration of which VMs exist and what properties they have and the inner refers to the NixOS configuration inside each VM.
The outer configurations are under the nix namespace of `qixosConfigurations` the inner ones are under `qixosTemplateConfigurations`, `qixosAppConfigurations`, or `qixosStandaloneConfigurations` but these are pretty thin wrappers around a regular `nixosConfigurations`.

This seems like a natural distinction for a number of reasons.
1. We are adding the qixosConfigurations concept on and we are piggybacking on the already existing nixosConfiguration concept.
2. The `qixosConfigurations` needs to live in a place accessible by the `qixos-admin` VM which uses `qixos-rebuild` since that's what consumes `qixosConfigurations`.
The inner config does not necessary have to live in a place accessible by the admin.

## Design decision 2
The `qixosConfigurations` attrset does not accept the inner config as nix code but rather as a string containing a url pointing to a flake for where the inner configuration can be found.

An alternative design could have had this inner configuration be expressed in nix code rather than as a string.

The positive consequenes of this decision are:
The admin VM does not evaluate any code related to the inner configuration, it just handles a string which it passes onto the template or standalone VM which in turn pulls from the pointed to flake URL.
Since the admin VM does not evaluate any code from inner configs we have a higher level of security and can more comfortably fulfill desiderata 3.

The biggest negative with this approach is the inability for the outer config to pass parameters to the inner config.
For example in an ideal world the inner config could define some conditional configuration and the outer config enables or disables this.
The way it works now all of that will have to be set in the inner config.

We're basing this decision on desiderata 2 and 3. The reduction of attack surface for the admin VM and the isolation of the inner config are sufficient to sacrifice the ergonomic loss.

If there was a way to usefully replace the flake url string with nix code but that nix code is never built and ideally never evaluated then we might reconsider this decision.

## Design decision 3
Templates are told which AppVMs will depend on them and builds the configuration for all of the AppVMs inside of the nix build sandbox.
They then symlinks this configuration with the each AppVMs name.
AppVMs will on boot lookup their built configuration and switch to it.
This is done with a systemd job called `qixos-appvm-switch.service`.

An alternative approach to this is to let a nixos template naively function like all other templates. The template controls the root, each AppVM uses the template configuration and only configures the home directory without touching the `/nix/store/`.

The positive consequences of using our design are:
1. Each AppVM is able to control their own configuration fully. I.e AppVMs do not need to share root config.
AppVMs can run root systemd services without the template having to run these. E.g the wireguard daemon.
2. Configuring an AppVM is as simple as on NixOS.
Each AppVM can declare exactly what packages they need rather than having to collect them all in the TemplateVMs config.
3. The TemplateVM is able to utilize the nix build sandbox in order to build each AppVM configuration in isolation.
4. The TemplateVM can switch into a minimal configuration which has a very small attack surface.
5. The same minimal TemplateVM config can be used for essentially all TemplateVMs.
6. The AppVMs all share the same `/nix/store/` in a maximally efficient way.

The negative consequences of this are:
1. The `/nix/store/` is shared by all AppVMs meaning each AppVM can see the total configuration of all AppVMs that it shares template with.
2. Each TemplateVM needs to know what AppVMs will depend on it.
3. It introduces runtime complexity by having each AppVM run a systemd job which calls `nixos-rebuild test` on each boot.

There are 2 security considerations introduced by this design decision. They both arise due the the shared `/nix/store/`.
1. If a secret is put in the `/nix/store/` then these can be read by the TemplateVM and all AppVMs that share the template.
It is important that the user is aware of this risk and does not put plaintext secrets in their config.
In the nix ecosystem the `/nix/store/` is considered "world-readable" and it is therefore considered bad practice to put secrets in the config.
For that reason the nix tooling will not put secrets there and there are multiple tools like `agenix` and `nix-sops` which can be used to encrypt secrets before putting them in the store should the need really arise.

2. If an AppVM is employing security through obfuscation then other AppVMs will be able to read the config and therefore de-obfuscate.
This is not a recommended practice in any serious security engineering anyway.

## Design decision 4
When `qixos-rebuild` switches a TemplateVM or StandaloneVM it uses `qixos.Switch` to generate `/var/qixos/current-flake/flake.nix` which acts as an intermediare step before calling `nixos-rebuild boot` on that flake.

This both simplifies the switch flow by dividing it up into parts.
It makes debugging easier because the generated flake acts as the canonical source of truth for the VMs config.
It also lets the user switch to that state manually without having to evoke the `qixos.Switch` machinery.

## Design decision 5
The outer config lets each nube specify a remote url or a local path as a flake configuration source.
The local path option allows the `qixos-admin` to use a locally stored flake as configuration source for the VM.
The `qixos-admin` will follow the path and find its git root and copy that entire directory to the VM.
The VM will then keep a local copy and use that as an input for its generate flake.
This is managed by `qixos.Switch`.

The utility of this is that it allows users to mix and match remote and locally defined configurations.
In some cases the user may want to modify their config without pushing to a remote repo.
For example if they want to update the `flake.lock` without having write access to the repo.

## Design decision 6
The generated `current-flake/flake.nix` uses the template configurations nixpkgs as the canonical version and forces the dependent AppVMs to use that same version for nixpkgs.

The decision for what nixpkgs version to use can be done in 3 places:
1. The TemplateVMs nixpkgs
2. The AppVMs nixpkgs
3. QixOS mandated nixpkgs inserted into the generated flake

1) seems like the best place to put this since it allows all AppVMs to use the same version and therefore reduces redundancy but also allows users to control which version of nixpkgs that they use by locking it in the templates config.

## Design decision 7
The `mkNubeApp` function can take a `directBuild` parameter which accepts a nixpkgs version.
This let's the returned value from `mkNubeApp` have a `nixosConfigurations.default` field.
This field exposes a regular NixOS configuration which can be used to switch directly to that AppVM config.
Note that this config will use its own nixpkgs version rather than that of its template VM which is different from the normal case where it uses its templates nixpkgs version.

This functionality is provided because it allows directly switching to an AppVM rather than going through the `qixos-rebuild` and `qixos.Switch` and `current-flake/flake.nix` machinery.
This makes debugging and testing easier as well as allows for more versatility.

## Design decision 8
QixOS ships each NixOS VM with a set of core nix modules. These modules include mostly necessary qubes specific configurations and packages.
This includes among other things the `system.stateVersion = "26.05"`.
Since the nixos template is constructed from the qixos repo it seems reasonable for qixos to control this variable.

It is an open question what exactly should be the default configurations qixos should ship.

## Design decision 9
The qixos systems are isolated from the rest of the qubes system. The qixos-admin VM is used to manage VMs with the tag "created-by-qixos-admin".
This is permissioned by the dom0 qubes qrexec policy.
The policy can be found in specificity in `install.sh` but the largest policy footprint is `qixos-admin @tag:created-by-qixos-admin allow target=dom0` inside of `/etc/qubes/policy.d/include/admin-local-rwx`.
The policy also allows limited access to `sys-net` so that qixos nubes can access the internet through it.

## Design decision 10
Updating a nube happens in 2 steps.
1. The relevant `flake.lock` file is updated for that nubes configuration. Note that to update the nubes `nixpkgs` version you must update the `flake.lock` of the TemplateVMs config.
2. `qixos-rebuild` is called with the `--update` flag. This pulls the newest version of the config.

## Design decision 11
QixOS is installed as an extension ontop of a regular QubesOS system.
You may use QixOS in parallel to QubesOS.

## Design decision 12
Home manager is not privileged in the inner configuration of a nube. A nube's inner configuration is a single list of `modules` which is evaluated as a plain `nixosSystem`.
Users who want home manager import it as a nixos module like any other nixos user, and users who don't want it never have to mention it.

QixOS used to have a `rootConfiguration` key alongside a `homeConfiguration` key, where the home configuration was evaluated by the standalone `home-manager` tool rather than as a nixos module.
That produced a second activation package per AppVM, a second symlink in the template's activation directory, and a second systemd job to run it.
It was removed because home manager is not a must-use for nixos users, and because using it as a nixos module works perfectly well.
The reason it was originally built with home manager as a privileged concept was a misguided attempt at making AppVM switching easier.

# Known issues

## One AppVM configuration failing causes the entire template build to fail
Each template builds all of the dependent AppVMs. If one of the AppVM configs fail to build then the entire template build will fail.
Ideally we'd have the template build flag the failure but continue to build with that AppVM config disabled.
