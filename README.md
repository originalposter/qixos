# QixOS
Qubes with Nix - the security and compartmentalization of QubesOS plus the configurability, shareability and packages of Nix

QixOS is a combination of QubesOS and NixOS. It is installed inside of QubesOS as an extension and provides tooling for managing your system with nix configurations.
QixOS makes some opinionated architectural decisions which are meant to increase security and improve ergonomics.
There is a [sister community repository](https://codeberg.org/originalposter/qixos-community) where users can share their nube (nix qube) configurations.

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
- https://codeberg.org/originalposter/qixos-community - community repository where you may upload your own configurations and download others configs
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

# License and acknowledgement
We use the GPL license.
There is code in this repository that was originally taken from evq's nixos template repository, that was published under MIT.

# OP's PGP key
I occasionally sign things, here is my pgp key.
-----BEGIN PGP PUBLIC KEY BLOCK-----

xjMEah8J0BYJKwYBBAHaRw8BAQdATL8KLgl6PGCdiYxiXGumba3Y6vtdY4FLCPIK
5eV+i0PCwAsEHxYKAH0FgmofCdADCwkHCRCoh83ak/FpmkcUAAAAAAAeACBzYWx0
QG5vdGF0aW9ucy5zZXF1b2lhLXBncC5vcmfHmolWS+SzKK/sdZorV7tFMejdGN7F
q+Ei5mJM1KlAHwMVCggCmwECHgkWIQRv8NMh6VjDOh74MPaoh83ak/FpmgAAYOEB
APYv9cvpxd6X4ya1r1jAu/dRra1tCD2M/rdZd1P/DKoWAP47BO8FaDfN9gQJjN6/
rno5ae50RiSmJv5MCzyLDcfEBc0OPG9wQHFpeG9zLm9yZz7CwAsEExYKAH0Fgmof
CdADCwkHCRCoh83ak/FpmkcUAAAAAAAeACBzYWx0QG5vdGF0aW9ucy5zZXF1b2lh
LXBncC5vcmeAU6EyARPJbvDa1lpEgVcOlAT3HOBZEaGGhp2UxvKUiwMVCggCmwEC
HgkWIQRv8NMh6VjDOh74MPaoh83ak/FpmgAAfyAA/jvMKBk/jd2yz3LunxS0BTDt
5+E26HDeSlb5nxr/C+STAP4h3WCUMDQnSYRxF7UvYIJWHhfGalPAzkW6HxXhSkbR
As0Cb3DCwA4EExYKAIAFgmofCdADCwkHCRCoh83ak/FpmkcUAAAAAAAeACBzYWx0
QG5vdGF0aW9ucy5zZXF1b2lhLXBncC5vcmfDiKhNNHYlRGauIx+NsTSEk9p8JGV5
U9Dpac4/gPDzygMVCggCmQECmwECHgkWIQRv8NMh6VjDOh74MPaoh83ak/FpmgAA
PgwBAMQDdACXLPa3nld8JwU0SJcztur4H5R2ipfkO/QPnza0APoCWyqeKUgdGI/i
ivsyq9ZHQEecj1UZm1ghTGcQBgVJBc4zBGoht30WCSsGAQQB2kcPAQEHQAh+LW9f
TzCt8BN68beQhg/wyLjoER6p1kIri9+w2lgOwsDFBBgWCgE3BYJqIbd9BYkAeGFN
CRCoh83ak/FpmkcUAAAAAAAeACBzYWx0QG5vdGF0aW9ucy5zZXF1b2lhLXBncC5v
cmcQwmgFj3HDLggSQV1uuQQInZNrUyPFtlg9oKy/dNDNqwKbAr6gBBkWCgBvBYJq
Ibd9CRDfFygbqxeS4UcUAAAAAAAeACBzYWx0QG5vdGF0aW9ucy5zZXF1b2lhLXBn
cC5vcmck6SMsQLsmA5kKFJjHbZ/zn+fxHJ3I8BZvyodaFIthOBYhBONQzAkdfzyC
K3CdNt8XKBurF5LhAAAifgEA1Bsu13+/E3TL7uICcbaNKOXPzKt0GwJvcTbAy0X2
B88BAJQbCXEbC/GH1UiIjMj8/ii8kmDz51HAzfMJvy2sXFIAFiEEb/DTIelYwzoe
+DD2qIfN2pPxaZoAAFbQAP4n0+kjGH6q6gvsKmzJrOVe/MmswNYGSMC868b3ZwIK
QgEAuAOuQCEP3B+MDYmHr4BeMn83crN1NsAMXqMheiYsNADOMwRqHwnQFgkrBgEE
AdpHDwEBB0Ck9Y++s5uPzwvXguTJDa6owHENNw+FVtr4EmKm8nc0kcLAvwQYFgoB
MQWCah8J0AkQqIfN2pPxaZpHFAAAAAAAHgAgc2FsdEBub3RhdGlvbnMuc2VxdW9p
YS1wZ3Aub3JnlYUZxdN1nlcTc50+a/+1AwLToCBHwpSQXtoKgrsxk5ECmwK+oAQZ
FgoAbwWCah8J0AkQKMldBL1XafFHFAAAAAAAHgAgc2FsdEBub3RhdGlvbnMuc2Vx
dW9pYS1wZ3Aub3JnFB9NbapzoUrbsCLuaLDg5sxTNFneZyDKqOkziueCbfEWIQS2
DjPZNFBL6NulmcAoyV0EvVdp8QAAMgkA/i5aoD/iaSwqfmO5shOcl+j8YNNdkkMr
3FeTGUS84Ig3AQD2z3TyfQ7+aqmGtpjkOY1tJAiuKjsvSiRijuJG4jFMBxYhBG/w
0yHpWMM6Hvgw9qiHzdqT8WmaAABHCwEA3otNYIJe6+VLRt7D0v2YOsRtlW6tGDCh
srFlnRvwS/gA/2z1JTnLzkrg0frZZQanKM0rq2ofYJjWoNBhWKScQB8EzjMEah8J
0BYJKwYBBAHaRw8BAQdAqFYWu7tBM6rCxMHvhWclqKFBt+DfY3g4p4vbAb71nqDC
wL8EGBYKATEFgmofCdAJEKiHzdqT8WmaRxQAAAAAAB4AIHNhbHRAbm90YXRpb25z
LnNlcXVvaWEtcGdwLm9yZ+8fgMN7q8gv53gGZsXvWe2GB86ODixIUr3dlhYCnSnA
ApsgvqAEGRYKAG8FgmofCdAJELg6L7Ro9i73RxQAAAAAAB4AIHNhbHRAbm90YXRp
b25zLnNlcXVvaWEtcGdwLm9yZ+T5O7PW5ACuJCBE9oOVOiDtiBb7OvbnFhacwr9n
cAcMFiEEKJPpM+v5yjbOOmlHuDovtGj2LvcAANx4AP9ZCrxnoaHSo42vRDvSMGes
eaTQY8cZ6nqyUhOPluLWSgEAivgWcmoxhA1X3HJUesBMorSK5hSBg6+0iwU6feZD
MAoWIQRv8NMh6VjDOh74MPaoh83ak/FpmgAA0vgBAK4fmPq3s73RPotPZhxIqZ7l
lMdYw6p2ej2l09ltjglRAP4kDNZis1eVYQRwMGxrtKiN0LTm4ee/ULybT2EUq/j9
Dc44BGofCdASCisGAQQBl1UBBQEBB0DOHdukdjUVkBR680R4nB0r4E0Exn4oUolV
eh0favK7fgMBCAfCwAAEGBYKAHIFgmofCdAJEKiHzdqT8WmaRxQAAAAAAB4AIHNh
bHRAbm90YXRpb25zLnNlcXVvaWEtcGdwLm9yZ9a8lto++fRRwUAzaSx3yeZyVr0G
IbEONVdsk26vXnviApsMFiEEb/DTIelYwzoe+DD2qIfN2pPxaZoAAD9ZAQCmHkVU
Px3PLJMHqlcLInGqSq+eLFmQejgz/U8aXB+52AD/Reat6whBOMU1BoyPdOLrSqN4
4Q4CU8rBTmUxm7iLVgs=
=JFt5
-----END PGP PUBLIC KEY BLOCK-----
