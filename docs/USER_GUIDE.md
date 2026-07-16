# Inner and outer configurations
QixOS uses two types of configurations for managing your system.
- The outer configuration - `.nix` configuration which describes which nubes (nix qubes) exist and what Qubes properties they have
- The inner configuration - `.nix` configuration which describes the internal system state of a nube.

The inner configuration contains a list of `modules` which are used the `nixos-rebuild` to build the nixOS state.
Since normal nixos configurations are also divided up into modules we are able to reuse code from the larger ecosystem.

The outer configuration is in a QixOS specific format and is consumed by the Qix tool `qixos-rebuild`.


# `qixos-rebuild` tool
In order to apply the configuration files to your system you use `qixos-rebuild --flake <outer-conf.nix>`.
It takes 3 commands, `apply`, `switch`, `diff`. `apply` first applies all the outer configuration changes such as creating and deleting VMs and changing their properties. It then switches each template VMs inner configuration by running `nixos-rebuild switch` inside the nube.
`switch` only does the latter step of `apply`.
`diff` does a dry-run and shows what outer configuration properties would be changed if you ran `apply`.


## Flakes
QixOS in general assumes flakes and uses these heavily. Flakes are a nix concept for how to expose a nix configuration file from different URLs.
This lets us store our outer and inner configurations in different locations and refer to them with flakes.


# Security
QixOS is installed on a QubesOS system. The QixOS security model does not allow any QixOS VM (called nube) access to any non-QixOS part of the system.
There are special exceptions to this. Right now it's only `sys-net` being used as a network VM by the nubes.

QixOS is managed through an admin nube which we call `qixos-admin`.
You may have multiple QixOS admin nubes on the same system. Each admin has total write and read access to nubes with the `@created-by-<qixos-admin-name>` tag.

`qixos-admin` can create and delete VMs with the `@created-by-<qixos-admin-name>` tag.

A difference between Qubes and Qix is that in Qix the TemplateVMs need to know the nix configuration of any AppVM that depends on it.
The TemplateVM will hold that config in it's `/nix/store/` which is readable by any AppVM depending on that TemplateVM.
The consequence of this is that any AppVM which depends on the same TemplateVM as another AppVM can read that other AppVMs entire `/nix/store/` including their configuration.
Ergo the `/nix/store/` can not hold secrets. This is normal in the Nix world and tooling in general treats the `/nix/store/` as "world-readable".
The Templates may write to the AppVMs, the AppVMs may read from the Templates but the AppVMs can not read from each other.

The StandaloneVMs are only read and writeable by `qixos-admin` and `dom0`.


# Workflows
## First setup
In order to get started follow the install instructions in `./install/INSTALL.md`. That should end you up with a `qixos-admin` VM in which you run `qixos-rebuild`.
Run `qixos-rebuild --flake <path-to-outer-config> apply` in order to apply the outer config.


## Adding a new VM
In order to add a new VM to your setup you need to change your outer config. Add a `AppVms.myNewVm` attribute to the appropriate template's `nubeCluster.templateName` attribute set.


## Modifying a VM
To change a nube you change it's inner configuration file and run `qixos-rebuild switch`.
This will start the TemplateVMs and `nixos-rebuild` them with the new configuration. You wait for the TemplateVMs to shut down and then restart your AppVM.


## Updating 
In order to update a nube you need to update that nubes `flake.lock`. If you're updating `nixpkgs` then make sure to update the `flake.lock` of the template since all AppVMs use the `nixpkgs` of the template.
If you don't have write access to the repo containing the `flake.lock` then you can switch to using a local version of the nube config.
Once the `flake.lock` has been updated you pass the `--update` flag to `qixos-rebuild` for either `apply` or `switch`.
This will update the generated `/var/qixos/current-flake/flake.lock` to point at your updated flake.


## Remote and local flakes
Each `AppVms` attribute has a `localFlake` or `remoteFlake` field attribute. The former has a `path` attribute, the latter a `url` attribute and both have a `output` attribute.
`url` is a string containing a url of the same format which regular nix flakes use.
`path` should be a string which contains a path which points to the directory containing the flake that should be loaded onto the AppVM from the admin VM.
The `localFlake` also has an optional attribute called `copyDir` which takes a string which contains an absolute path to a local directory.
If `copyDir` is given then `path` must be a local path relative to the `copyDir` directory.

localFlake internally works by copying the git root of the outer config's flake.nix (or the specified `copyDir`) to the TemplateVMs `/var/qixos/current-flake/local-repos/` directory.


## Debugging
There are 3 places that are likely good starting points for debugging a problem.
1. The logged outputs from `qixos-rebuild` in the admin VM. This should tell you if there are configuration errors in the outer config.
2. In the problem TemplateVM lookup the generated `flake.nix` file in `/var/qixos/current-flake/`.
This flake represents the entire template state and running `nixos-rebuild` on it with the `#template` output is the canonical way to switch the template.
3. In the problem AppVM check `sudo systemctl status qixos-appvm-switch.service`. This is a systemd job that runs on AppVM startup and switches from the templates NixOS configuration to the AppVMs configuration. If it fails you can look at the logs with `journalctl -u qixos-appvm-switch`.
If the job fails you may try to run `sudo systemctl restart qixos-appvm-switch.service` to restart it, if it then consistently succeeds it is indicative of a race condition in the switching.
