# QixOS
Qubes with Nix - the security and compartmentalization of QubesOS plus the configurability, shareability and packages of Nix

QixOS is a combination of QubesOS and NixOS. It is installed inside of QubesOS as an extension and provides tooling for managing your system with nix configurations.
QixOS makes some opinionated architectural decisions which are meant to increase security and improve ergonomics.
There is a [sister community repository](https://github.com/originalposter/qixos-community) where users can share their nube (nix qube) configurations.

*Status: Public alpha. Expect that things are buggy and unstable. Don't use for security critical tasks*

# Installation
You install QixOS as an extension of QubesOS.
It is managed through a qixos admin VM which is able to create other QixOS VMs.
No QixOS VM has access to your other Qubes VMs except for the ability to send network traffic through `sys-net`.
To see how to install QixOS look in the `./install/INSTALL.md` file.

# Where can I read more?
- [VISION](docs/VISION.md) - lays out the high-level vision of the project and talks about what QixOS can achieve.
- [DESIGN](docs/DESIGN.md) - describes the design of the system, the architecture, the tradeoffs and the reasoning.
- [USER GUIDE](docs/USER_GUIDE.md) - quick guide for how to use the basic flows on QixOS
- [INSTALLATION GUIDE](install/INSTALL.md) - installation guide

# Repository layout
- `core` - holds the qixos code and is separated into 2 languages and 3 parts
  - `qixos-rebuild` - python cli for deployment.
  - `qixos-nix-libs` - nix libraries for making the various configurations.
  - `qubes-modules` and `qubes-pkgs` - nix code for packaging qubes tooling to make nixos work on qubes.
- `testaments` - here you can leave your gpg signed reviews of the code. We want regular users to look at the code and give their thoughts.
Especially with a focus on the security of the project. Hopefully this can give people an impression on how many eyes have been on the code.
- `install` - holds code and documentation needed for installing QixOS
- `docs` - holds general documentation for QixOS
  - `CHANGELOG.md` - what changed in each release, and what upgrading asks of you

# Features
- NixOS templates on QubesOS.
- `qixos-rebuild` tool which lets you configure your QixOS VMs using a `.nix` flake.
- Improves template security with space-time security concept. See `docs/VISION.md` for details.
- Lets AppVMs configure their own root filesystem instead of having to go through `bind-dirs` and `/rw`.
- Combines the modularity of QubesOS VMs with the modularity of NixOS modules.
- Community repository which lets QixOS users share their VM setups in a modular way.

## Anti-features/tradeoffs
- Templates are dependent on the NixOS configuration of all AppVMs that depend on them. Templates and all AppVMs can see the entire `/nix/store` and nix config of all other dependent AppVMs. As long as you don't store secrets in `/nix/store` or are using security by obscurity it should not be a problem.

# Community
- https://github.com/originalposter/qixos-community - community repository where you may upload your own configurations and download others configs
- https://discord.gg/HKS9GDena - discord server where you can bring your questions in order to get fast feedback
- https://forum.qubes-os.org - QubesOS forum for finding other Qubes enthusiasts and discussing Qubes

# Known issues and limitations
There are some important limitations in the alpha, this is not an exhaustive list and for a more up-to-date view use the issue tracker.
- Currently disposable VMs have not been tested.
- Currently not all VM properties can be set. Diskspace for example must be set through normal qubes means
- Currently StandaloneVMs will not resize their disk automatically.

# Contributing
The way to contribute will evolve as this project grows. Currently the most desired contribution is feedback.
Please get in touch and tell me what you think both about the vision and purpose of the project as well as the architectural decisions made in the project.
Code contributions are also welcome but be warned that I'll push back on feature creep.

# Use of LLMs
QixOS 0.2.0 and after is written together with LLM coding assistants such as Claude Code.

Changes are made together with an LLM, not by an LLM, and every code change is understood before it is merged.
The one exception to this is documentation which is not security critical. It is still read but not as carefully.
No LLM agent has push access to this repository.

This matters here more than it would in most projects since QixOS is fundamentally a security project which asks for your trust.
LLMs introduce a new supply chain dependency and potentially introduce systemic risks where LLMs have blind spots.
For these reasons the use of LLMs may change the security profile for some users and it is important that they are aware of this in order to make an informed choice.

Contributions written with LLM assistance are welcome. The standard is the same as for any other contribution: you understand the code,
you can defend it in review and you have tested it. State which model(s) you've used in the PR description.
Do not open PRs containing output you have not read yourself.

# License
Copyright (C) 2026 op (op@qixos.org)

QixOS is licensed under GPL-2.0-or-later.

QixOS is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 2 of the License, or (at your option) any later version.
See [LICENSE](LICENSE) for the full text.

## Acknowledgement
Parts of QixOS derive from [evq's qubes-nixos-template](https://github.com/evq/qubes-nixos-template),
Copyright (c) 2024 eV Quirk, originally published under the MIT license:

- `install/build-nix-template/` - carries its own
  [LICENSE](install/build-nix-template/LICENSE), plus further notices in
  `install/build-nix-template/tools/iso.nix` for code from misuzu and the
  Nixpkgs/NixOS contributors.
- `core/qubes-modules/` and `core/qubes-pkgs/` - each derived file carries an
  attribution header naming its origin.

MIT permits redistribution under the GPL, so these portions ship as part of QixOS
under GPL-2.0-or-later. The original MIT permission notice is retained at
[install/build-nix-template/LICENSE](install/build-nix-template/LICENSE) and applies
to all evq-derived code in this repository.

# OP's pgp fingerprint
Full key can be found under `testaments/pubkeys/op.asc`
```
6FF0D321E958C33A1EF830F6A887CDDA93F1699A
```
