# QixOS
Qubes with Nix - the security and compartmentalization of QubesOS plus the configurability, shareability and packages of Nix

# How Qubes and Nix synergize
QubesOS and NixOS solve orthogonal problems.
QubesOS provides security and compartmentalization while NixOS provides configuration-as-code and packaging.

## Space-time security
There are also certain architectural decisions in Qubes and Nix which serendipitously fit perfectly together.
Most notable is that Qubes could be thought of as having a concept of 'spatial security' in the form of TemplateVMs and AppVMs.

Nix can be thought of as having a complementary concept we could call 'temporal security'.
Nix does 'building' of configurations and 'activation' of configurations at different times.
These are called 'build-time' and 'activation time' and have different security properties.
Nix will build packages inside of a build sandbox which has no side-effects except leaving built artifacts in a specific output directory in the `/nix/store/`.
NixOS also has an 'activation time' where it instantiates a built derivation onto your system.
It is at activation time that malicious packages are run outside of a sandbox and are able to do damage.

QixOS makes great use of these by combining them into a concept of 'space-time security'.
What space-time security means is that Qix pairs up the most sensitive spatial qubes domain, the TemplateVM, with the high security temporal domain - build-time.
The activation time happens only once the AppVM boots. A malicious package therefore activates only inside its own AppVM, and is unable to compromise the template or any other AppVMs.

## Each AppVM chooses its root
Another synergy that Nix unlocks in Qubes is the ability for AppVMs to control their own root (`/`) directory.
In stock Qubes the root directory is controlled by the TemplateVM and AppVMs share it. Modifying `/etc/` or similar is something left up to the TemplateVM.
There is a workaround AppVMs can use; `bind-dirs` and `/rw/` can be used to modify specific parts of the root directory.
However this is somewhat complex and annoying, especially for larger configurations.
In QixOS we leverage the NixOS switch to let each AppVM control exactly how its root directory looks.
Configuring it is just writing an ordinary NixOS configuration.


Above are only two of many synergies that Qubes + Nix offer. Some others include:
- shareability + isolation - you are able to fearlessly use other people's configs since they are isolated to their own AppVM
- declarative config for a large fleet of VMs - VM management in Qubes can get frustrating but declarative config as code makes larger scale management easier
- config as code + isolation + qubes secret management - these let you run LLM agents in a secure environment and allow them to self-modify their own configs
- specialized qubes defined as a nix module - you can define a specialized qube like `split-ssh` as its own nix module which leads to a clear and clean interface

# Why I built QixOS
I built QixOS because I really love Qubes and I started falling in love with Nix.
I write this mainly for a qubes audience so I'll focus on what I love about nix.

Nix is all about configuration as code. I love that this leads to a declarative source of truth for what your system looks like.
No more forgetting if you installed something, now you can go to the config and see exactly what the current state of your computer is.
I love that it lets you configure in a turing complete language.
This means that as you figure out your configuration and you realize that there is some recurring pattern you can write a library for it.
You can extend it to your heart's content.

I love that you can share what you write.
You can download libraries from others.
Suddenly configurations become much more scalable.
You don't need to rely as much on guides that tell you how to configure or install something.
Now you just include a nix module in your configuration and it handles it for you.

I love that it's all tracked and built from source, I think this is more of an ideological point, not a day-to-day ergonomic benefit.
However I really love that the dependency tree is explicit and required.
All packages have their build scripts as open source and all packages describe exactly what dependencies they need.
As an eco-system I vastly prefer it to the old model of the apt and dnf repos.

I love that it's trying to be deterministic.
Computer operating systems are by their very nature chaotic and live.
They change over time, usually for the worse, this leads to the fact that you need to re-install every couple of years.
Nix strives for determinism even if it does not achieve it perfectly it trends in that direction, it forces you to adhere to it and it gets a long way there.
This means it's much easier to reason about the system, find bugs, reproduce bugs and manage the system even at a distance.


# Future plans
Here are some dreams and ambitions for the future of QixOS with ideas for what directions we could take this project.

## Community repo
My ambitions for the project in the future include a community of like-minded individuals that are able to share their configurations and projects easily and securely.
Sharing a setup for some specific purpose is as easy as making a 'nube' (nix qube managed by QixOS) configuration and publishing it with a PR in the public qixos-community repo.
Other users can download and use this nube without fear that it'll compromise their system outside of the AppVM it is installed in.
People can wrap software they want to publish in a nube configuration and this can be found and used securely by other users.
The nube gets to configure an entire environment tailored to that software, which is something a traditional package manager can't offer.

One of the downsides of the qixos-community git repo is that it creates a bottleneck for updating configs since you need to go through a PR process.
It is my intention to let people have their own name-space'd directory and for them to essentially have free control over anything under that directory.
I would basically rubber-stamp PRs that only touch things under your namespace unless they contain obvious malware.

I am interested in hearing ideas for alternative ways to have unified repo structure but that alleviate the bottleneck of having to go through PRs.

## Special qubes
I would like to make the various special qubes accessible as nix modules and nube configs. Examples being network qubes, `sys-audio`, `sys-gui`, `split-ssh`, etc.
This would hopefully make the more complex qubes available to less technically savvy people with less time on their hands.
`sys-gui` is especially interesting as it would unlock a bunch of usecases that require configuring the graphical aspects of QubesOS.

## Special commands
I would like to experiment with how to better package software for users.
The fact that a nube configuration gets to control the entire environment opens up new possibilities.
For example a nube could ship a `halp` bash command which explains how to use the nube.
The `halp` command could in some contexts only be an `echo` call but in others could open an interactive user interface for helping the user.
`setup` could be another command that can be shipped in the case where the nube needs some setup.
`test` is another command for running specific tests for making sure that nube is working as intended. This could be used by the qixos testing framework as well as by the user. I would like to figure out more of these kinds of commands that could be useful.

## LLM agent friendly
I hope that QixOS can be usefully paired with LLM agents since it offers a combination of: secure isolation, configuration as code letting the LLM control its own environment, the sophisticated secret management of QubesOS, qrexec as an interface to securely let LLMs act on your computer in a controlled manner.

## Testing
I would like to make a testing framework that allows testing a qixos configuration before it gets deployed.
The testing framework should have two different parts.
The first runs tests for the core qixos logic.
The second runs tests defined in a nube's config.

I envision that a user could have a sophisticated testing setup where they use the isolated qixos-systems feature to create a 'staging' environment where they can test that their new configuration works as expected.
They could then deploy this configuration on their live system.

If you want to be fancy you could even use an LLM which has access to your testing admin VM. You could make requests and the LLM could implement these in nix code and run the testing for you in parallel.

## Secure and reproducible shared environments for orgs
I hope that qixos can be used by orgs to allow high security reproducible environments for example, dev environments that can be shared across teams.

# Philosophy
## Live in the code
I encourage you to not fear the nix code. Learn it bit by bit so that you eventually can understand how to extend your system.
Trying to hide behind abstractions is likely the wrong approach.
Nix is genuinely a great tool for configuring your OS (that's what it is made for) and the initial energy put into learning it pays off.

## Code testaments
I would like people to read the code and make a PR with a gpg signed message about what part of the code they looked at and potential vulnerabilities they found or the lack of these.
Hopefully this gives everyone a sense of how many eye-balls are on the codebase and over time can be used to give people a sense of the security of the system.
You are very welcome to use various LLMs to review the code. If you do then please include which LLM you used in the testament.

## Have fun
It is the ambition of this project to be fun.
You live in your operating system, it is in a sense your virtual home. I encourage people to experiment and do fun things, try out easter eggs, play around.
One of the benefits of having a highly isolated system is that you have to worry less about contaminating other environments or borking the system.
In QixOS you get your own little sandbox that you can mess about in.
