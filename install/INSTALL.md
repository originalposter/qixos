# Installation
You may choose between either an automatic install by running the `install.sh` script inside of dom0 or a manual
installation process by following the steps specified in the `Manual install` section.
The two installation methods attempt to take the same steps.

The installation script is farily readable and together with the manual description an audit should be doable
by a user with some motivation and technical knowhow of bash and the qubes RPC system.

If you do end up doing such an audit then please attest it in the `testaments` directory.
For further details read `testaments/README.md` in this git repository.
TODO: Create above

## Automatic install
### SECURITY CONSIDERATIONS - MAKE SURE YOU UNDERSTAND THIS
Running a shell script in dom0 comes with an assumption of trust for the file and the author of that file.
Make sure you are comfortable with the implications of those. This path is offered for the lazy and trustful.
Paranoid and curious users are encouraged to follow the manual install path.

### Copying to dom0
The installation file can be found at `install/install.sh`.
The file may be copied by running in dom0:
```
qvm-run -p <name of vm containing install.sh> "cat /home/user/path/to/install.sh" > dom0_qixos_install.sh
```

### Verifying the integrity of the installation script
You should check that the `sha256 sum` of the file is `6b1a8f35b8804b8c6892f272fa9dd2827dac97c089540e42e56a554a387d7fca` you may do this by running in dom0:
```
sha256sum dom0_install.sh
```

Below is a signature that this is indeed the hash. The public key can be found in the root README.md
```
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

sha256sum install/install.sh =
6b1a8f35b8804b8c6892f272fa9dd2827dac97c089540e42e56a554a387d7fca

-----BEGIN PGP SIGNATURE-----

wr0EARYKAG8FgmpZ27YJEN8XKBurF5LhRxQAAAAAAB4AIHNhbHRAbm90YXRpb25z
LnNlcXVvaWEtcGdwLm9yZyAGUKQ07rozVdZ9n+L9DARbRLQ8NqSDGv0W5f3o//Fh
FiEE41DMCR1/PIIrcJ023xcoG6sXkuEAANm7AP9+Ues48QEX5d1WkooMHJTR89Fv
wbQgBvVA/yo7FOWnfAEAoqlJDVyDwq9jcn+GSRBpaOITthC+DO/pgMlqrJz76Qs=
=b/1k
-----END PGP SIGNATURE-----
```

### Installation script structure
The installation script consists of 13 steps that correspond to the 13 steps in the manual install.
You can run up to and including step X by running `sudo ./dom0_qixos_install.sh X`. Omitting X runs all steps.
Once a step has been completed it will create a file called `STEP_X_COMPLETE` inside `/var/lib/qixos-install/`.
If you run the script another time it will skip all steps for which it finds such a file.

The script starts by setting some configurable bash variables. You can change these to various values if you
know what you are doing.

### Running installation script
Assuming the script is called `dom0_qixos_install.sh` you can install qixos by running the following in dom0:
```
chmod +x ./dom0_qixos_install.sh
sudo ./dom0_qixos_install.sh
```

## Manual install
### Step 1
Create 2 temporary standalone VMs which are used to build a nixos qubes template and install it on your system.
Make sure that the building VM has enough disk space in its root filesystem to build the template.
```
qvm-create temporary-qixos-nix-build --label red --template fedora-43-xfce --class "StandaloneVM"
qvm-create temporary-qixos-nix-install --label red --template fedora-43-xfce --class "StandaloneVM"
# 30 GB
qvm-volume resize temporary-qixos-nix-build:root $((30 * 1024 * 1024 * 1024))
```

### Step 2
In `temporary-qixos-nix-build` install nix, source it and then build the image from this repo.
```
sh <(curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install) --no-daemon
. /home/user/.nix-profile/etc/profile.d/nix.sh
nix --extra-experimental-features "nix-command flakes" --option system-features 'kvm benchmark big-parallel nixos-test' build --no-write-lock-file 'git+https://github.com/originalposter/qixos?ref=master&dir=install/build-nix-template'#rpm
```

### Step 3
Copy the produced `.rpm` file from `temporary-qixos-nix-build` to `temporary-qixos-nix-install`
In `temporary-qixos-nix-build`
```
qvm-copy /home/user/result/*.rpm
```

### Step 4
In `temporary-qixos-nix-install` install the `qubes-core-agent-client` package in order to get `qvm-template`
```
sudo dnf install qubes-core-admin-client
```

### Step 5
SECURITY CRITICAL - MAKE SURE YOU UNDERSTAND THIS SECTION WELL
#### Explanation
We need to install the nixos template onto our qubes system.
To do this we use the `install` functionality of the `qvm-template` tool. This tool installs a .rpm file as a template.
In order to sandbox the installation as much as possible we run this command from inside `temporary-qixos-nix-install`.

However to do a `qvm-template install` we must give the `temporary-qixos-nix-install` qube some permissions.
We do this by creating a new file in dom0 in the `/etc/qubes/policy.d/` directory.
This file contains permissions to execute some qubes RPC commands.

None of the permissions allow for writing to the larger system.
However you should look over the policies yourself to verify that this is indeed true.

You may read about how qubes RPC policies work in this guide:
https://doc.qubes-os.org/en/latest/developer/services/qrexec.html#policy-files

You may also read about the admin RPC specifically here:
https://doc.qubes-os.org/en/latest/developer/services/admin-api.html

The quick understanding of how a policy works is that each lines takes the following
form:
`service-name|* +argument|* source destination action  [options]`
The first part of each line is the RPC that is allowed, then comes a potential argument,
then comes the source VM for the RPC and then comes the destination VM.
After this all of our policies have `allow`.
The `target=dom0` is needed for all `admin.*` RPC permissions since it tells qubes
that the RPC should be processed by dom0 even if it targets another VM.
This is needed since most admin APIs must be processed by dom0.

In order to convince yourself that the below permissions are safe note and verify the following:
1. There are no modifications permitted to any qube except "nixos" (the template) and the creation of template VMs
2. There are no read or write operations permitted to any qube except for dom0 and nixos
3. The only operations permitted towards dom0 are read-only
4. Of the read-only operations permitted towards dom0 none allow seeing sensitive information except *perhaps* `admin.Events`
5. `admin.Events` allows the installation qube to see events such as the starting and stopping of VMs.
This is not particularly sensitive and will only be allowed temporarily during the installation of our template.

All of the below permissions are necessary for `qvm-template install` to function properly.

#### Actions to take
After reading the policy file put all lines not starting with # inside of
`/etc/qubes/policy.d/1-qixos-temporary-install.policy`:
```
# This operation modifies the larger system. But it only allows the creation of new templates.
# This is by itself not an unsafe operation.
admin.vm.Create.TemplateVM + temporary-qixos-nix-install dom0 allow target=dom0

# Read-only operation that lets our install VM "see" the existence of dom0
admin.vm.List + temporary-qixos-nix-install dom0 allow target=dom0

# Read-only operation on dom0 to get the name of the updatevm
admin.property.Get +updatevm temporary-qixos-nix-install dom0 allow target=dom0

# Read-only operation that lets our install VM see qubes events such
# as templates having been created, starting and stopping, etc.
admin.Events + temporary-qixos-nix-install dom0 allow target=dom0

# These permit modification but ONLY to the nixos template
qubes.PostInstall + temporary-qixos-nix-install nixos allow
admin.vm.Start + temporary-qixos-nix-install nixos allow target=dom0
admin.vm.Shutdown + temporary-qixos-nix-install nixos allow target=dom0
admin.vm.property.Set * temporary-qixos-nix-install nixos allow target=dom0
admin.vm.feature.Set * temporary-qixos-nix-install nixos allow target=dom0
admin.vm.feature.Remove * temporary-qixos-nix-install nixos allow target=dom0
admin.vm.property.Reset * temporary-qixos-nix-install nixos allow target=dom0
admin.vm.volume.ImportWithSize +root temporary-qixos-nix-install nixos allow target=dom0

# These are read-only operations on the nixos template
admin.vm.List + temporary-qixos-nix-install nixos allow target=dom0
admin.vm.volume.List + temporary-qixos-nix-install nixos allow target=dom0
admin.vm.CurrentState + temporary-qixos-nix-install nixos allow target=dom0
```

After creating the policy run the following command inside of `temporary-qixos-nix-install`:
```
qvm-template install /home/user/QubesIncoming/temporary-qixos-nix-build/<.rpm file> --nogpgcheck
```

Once the template install completes remove the temporary installation policy file.
In dom0 run:
```
sudo rm /etc/qubes/policy.d/1-qixos-temporary-install.policy
```

### Step 6
Remove `temporary-qixos-nix-build` and `temporary-qixos-nix-install`
In dom0:
```
qvm-shutdown --wait temporary-qixos-nix-build
qvm-shutdown --wait temporary-qixos-nix-install

qvm-remove temporary-qixos-nix-build
qvm-remove temporary-qixos-nix-install
```

### Halfway point for creating various admins
QixOS lets you create multiple admin VMs and each controls its own set of nubes (nix qubes).
The installation from step 1 to 6 is general and can be re-used.
The remaining steps are for installing a specific admin VM. In the following tutorial we call it `qixos-admin`.
However you can call it whatever you want, in that case whenever you see `qixos-admin` and `qixos-admin-base-template` replace it with whatever name you chose.

If you want to create multiple admins just repeat steps 7 and onwards but for different admin names.

### Step 7
Create a TemplateVM based on `nixos` called `qixos-admin-base-template`.
```
qvm-clone nixos qixos-admin-base-template
```

### Step 8
Make sure `qixos-admin-base-template` is shut down and then resize the disk of the root filesystem to hold at least 30 GB
```
qvm-volume resize qixos-admin-base-template:root 30GiB
```

### Step 9
Do a first `nixos-rebuild boot` of `qixos-admin-base-template` to initialize the system.
Take a root shell rather than prefixing with `sudo`, since nix commands under `sudo` run
into trouble (see `install/build-nix-template/README.md`).
```
sudo su
nixos-rebuild boot --flake /etc/nixos#nixos
```
Then shut down the template.

### Step 10
Now that the template has been initialized load a template configuration onto the template.
You can use your own configuration for a qixos template or you can use mine (op /author)
I'll illustrate with my own.
Inside `qixos-admin-base-template`:
```
sudo nixos-rebuild boot --flake "git+https://github.com/originalposter/qixos-community?ref=master&dir=users/op/nubes/templates/basic"#default
```

Then shutdown the template

### Step 11
Create the `qixos-admin` VM from `qixos-admin-base-template`.
In dom0:
```
qvm-create qixos-admin -t qixos-admin-base-template --label black --standalone
```

### Step 12
SECURITY CRITICAL - MAKE SURE YOU UNDERSTAND THIS

Now we need to create two permanent policy files to give permissions for `qixos-admin` to manage the VMs it creates.

#### admin-local-rwx
In dom0 first add 1 line inside of `/etc/qubes/policy.d/include/admin-local-rwx`:
```
qixos-admin @tag:created-by-qixos-admin allow target=dom0
```

IMPORTANT: this allows the 'local' read and write operations from `qixos-admin` to any VM created by `qixos-admin`.
The `target=dom0` is needed since the admin API routes through `dom0`.
To know which operations count as 'local' you can look in the `90-admin-*-default.policy` files and see how they include `include/admin-local-rwx`.
#### 55-qixos-admin.policy file
Then create a file at `/etc/qubes/policy.d/55-qixos-admin.policy` with the following text:
If you want you may ignore the comments and only write the lines not starting with a `#`.
```
### POLICY FILE FOR qixos-admin ###
# This policy file should enforce a 0-trust policy for the qixos system.
# This means that the user of the qubes system should not need to trust
# that any qube managed by qixos-admin is non-malicious for their
# non-qixos qubes to be safe.
#
# What it means to be be "managed by qixos-admin" is that the qube
# has the tag "created-by-qixos-admin". This tag is automatically
# attached to any VM created by qixos-admin by dom0. It can not
# be added to other VMs by qixos-admin.
#
# What this means concretely is that this policy should allow
# 1) No write access to any part of the system outside of
#    a) Creating new VMs
#    b) Write and read access to VMs managed by qixos-admin
# 2) No read access to any VM *not* under the management of qixos-admin
#    outside of reading global qubes properties and qubes properties of dom0.
#
# Properties here refers to the `admin.vm.property` and `admin.property` APIs as well
# as similar APIs such as for example `admin.label.List`.
#
# An example of these are reading the default `netvm` or default template.
# This does *not* mean being able to read any file in dom0.
#
# The above description is a high-level goal for what the file is *meant* to do, but the actual
# source of truth for what it *does* is below and should be scrutinized carefully.

# Allow the creation of VMs. The tag "created-by-qixos-admin" is applied automatically.
admin.vm.Create.AppVM * qixos-admin dom0 allow
admin.vm.Create.StandaloneVM * qixos-admin dom0 allow
admin.vm.Create.TemplateVM * qixos-admin dom0 allow

# Allow read-only access to some global properties of the qubes system
admin.label.List + qixos-admin dom0 allow
admin.vmclass.List + qixos-admin dom0 allow
admin.property.Get +default_pool_private qixos-admin dom0 allow
admin.property.Get +default_pool_volatile qixos-admin dom0 allow
admin.property.Get +default_pool_root qixos-admin dom0 allow
admin.property.Get +default_netvm qixos-admin dom0 allow
admin.deviceclass.List + qixos-admin dom0 allow target=dom0

# Allow read-only access to some dom0 properties.
admin.vm.List + qixos-admin dom0 allow
admin.vm.tag.Get +created-by-qixos-admin qixos-admin dom0 allow target=dom0

# Allow read access to some sys-net properties
admin.vm.List + qixos-admin sys-net allow
admin.vm.tag.Get +created-by-qixos-admin qixos-admin sys-net allow target=dom0
admin.vm.property.Get +provides_network qixos-admin sys-net allow target=dom0

# Allow Remove and List access to VMs managed by qixos
admin.vm.Remove + qixos-admin @tag:created-by-qixos-admin allow target=dom0
admin.vm.List + qixos-admin @tag:created-by-qixos-admin allow target=dom0

# Allow access to internal qixos.Switch API to manage nix qubes
qixos.Switch * qixos-admin @tag:created-by-qixos-admin allow user=root
```

### Step 13
Add the `created-by-qixos-admin` tag to `qixos-admin` and `qixos-admin-base-template`.
In dom0:
```
qvm-tags qixos-admin add created-by-qixos-admin
qvm-tags qixos-admin-base-template add created-by-qixos-admin
```

# After installation
Once you are done you should have 3 new qubes: `qixos-admin`, `qixos-admin-base-template`, and `nixos`.
`nixos` is not used by QixOS at all after this. It is a basic nixos template that you can use for whatever purpose you want.

To get started you can clone the community repository and setup an example repo
Inside qixos-admin:
```
git clone https://github.com/originalposter/qixos-community
cd qixos-community
qixos-rebuild --flake ./users/op/outer-configs/example#example apply 
```
This will apply my (the author's) qixos configuration to your system.
This means it will create new nubes as specified inside of the file pointed to by `--flake`.

# Troubleshooting
If you encounter issues during the install from the script you can try shutting down whatever VM was running in the step that failed and then re-running the script. The install script will pick up where it left off.

If you are encountering 403's during the build download it may be due to trying to reach servers through a tor exit then you can change your updatevm through qrexec policy.
This means saving a file such as:
`/etc/qubes/policy.d/40-qixos-non-tor-update.policy`
with the content:
`qubes.UpdatesProxy * <templateVM> @default allow target=sys-net`
