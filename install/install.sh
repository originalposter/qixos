#!/bin/bash

# This script is supposed to be run inside of dom0.
# It will install qixos on your qubes system.
# This is the trustful automatic installation option.
# You may also do a *trustless* install by following the manual installation steps described in
# in the installation documentation in this directory.

# This install script strives to be idempotent - meaning you can rerun it over and over and it should function the same
# as if you ran it only one time.
# As we complete each step in the install process we mark it as such in $COMPLETED_INSTALL_STEPS_DIR (default: /var/lib/qixos-install/)
# Each install step roughly corresponds to each step in the manual install process.
#
set -eu
# Directory where STEP_X_COMPLETE files are stored
COMPLETED_INSTALL_STEPS_DIR="/var/lib/qixos-install"

# Name of temporary nixos template build and installation standalone qubes
NIX_BUILD_QUBE_NAME="temporary-qixos-nix-build"
NIX_INSTALL_QUBE_NAME="temporary-qixos-nix-install"
# Name of the template the above qubes will be based on - reasonable to change but should be fedora
INSTALLATION_VMS_TEMPLATE="fedora-43-xfce"

# Name of the final qixos admin qube - reasonable to change
QIXOS_ADMIN_NAME="${QIXOS_ADMIN_NAME:-"qixos-admin"}"
# The base template is used as clone basis for making new templates
QIXOS_BASE_TEMPLATE="$QIXOS_ADMIN_NAME-base-template"

# URL to the flake that the qixos admin template will switch to - very reasonable to change, but make sure it points
# to a correct nube template configuration and that the url is accessible (not a private git repo)
QIXOS_ADMIN_FLAKE="${QIXOS_ADMIN_FLAKE:-"\"git+https://github.com/originalposter/qixos-community?ref=master&dir=users/op/nubes/standalones/qixos-admin\"#default"}"

# Name of the qixos admin policy file in dom0 - reasonable to change but primarily to change the number it starts with
# to affect policy evaluation ordering.
QIXOS_ADMIN_POLICY_FILE="/etc/qubes/policy.d/55-$QIXOS_ADMIN_NAME.policy"

# NOTE: This policy file may not be complete. We may find that qixos management may need additional policies.
# Reasonable to change but make sure you know what you are doing. Making the wrong changes here could lead to
# COMPLETE SECURITY FAILURE!
#
# TODO: Is there a better way to deal with the guivm and audiovm policies?
#admin.vm.tag.Set +guivm-dom0 $QIXOS_ADMIN_NAME @tag:created-by-$QIXOS_ADMIN_NAME allow target=dom0
#admin.vm.tag.Set +audiovm-sys-audio $QIXOS_ADMIN_NAME @tag:created-by-$QIXOS_ADMIN_NAME allow target=dom0
QIXOS_ADMIN_POLICY="### POLICY FILE FOR $QIXOS_ADMIN_NAME ###
# This policy file should enforce a 0-trust policy for the qixos system.
# This means that the user of the qubes system should not need to trust
# that any qube managed by $QIXOS_ADMIN_NAME is non-malicious for their
# non-qixos qubes to be safe.
#
# What it means to be be \"managed by $QIXOS_ADMIN_NAME\" is that the qube
# has the tag \"created-by-$QIXOS_ADMIN_NAME\". This tag is automatically
# attached to any VM created by $QIXOS_ADMIN_NAME by dom0. It can not
# be added to other VMs by $QIXOS_ADMIN_NAME.
#
# What this means concretely is that this policy should allow
# 1) No write access to any part of the system outside of
#    a) Creating new VMs
#    b) Write and read access to VMs managed by $QIXOS_ADMIN_NAME
# 2) No read access to any VM *not* under the management of $QIXOS_ADMIN_NAME
#    outside of reading global qubes properties and qubes properties of dom0.
#
# Properties here refers to the \`admin.vm.property\` and \`admin.property\` APIs as well
# as similar APIs such as for example \`admin.label.List\`.
#
# An example of these are reading the default \`netvm\` or default template.
# This does *not* mean being able to read any file in dom0.
#
# The above description is a high-level goal for what the file is *meant* to do, but the actual
# source of truth for what it *does* is below and should be scrutinized carefully.

# Allow the creation of VMs. The tag \"created-by-$QIXOS_ADMIN_NAME\" is applied automatically.
admin.vm.Create.AppVM * $QIXOS_ADMIN_NAME dom0 allow
admin.vm.Create.StandaloneVM * $QIXOS_ADMIN_NAME dom0 allow
admin.vm.Create.TemplateVM * $QIXOS_ADMIN_NAME dom0 allow

# Allow read-only access to some global properties of the qubes system
admin.label.List + $QIXOS_ADMIN_NAME dom0 allow
admin.vmclass.List + $QIXOS_ADMIN_NAME dom0 allow
admin.property.Get +default_pool_private $QIXOS_ADMIN_NAME dom0 allow
admin.property.Get +default_pool_volatile $QIXOS_ADMIN_NAME dom0 allow
admin.property.Get +default_pool_root $QIXOS_ADMIN_NAME dom0 allow
admin.property.Get +default_netvm $QIXOS_ADMIN_NAME dom0 allow
admin.deviceclass.List + $QIXOS_ADMIN_NAME dom0 allow target=dom0

# Allow read-only access to some dom0 properties.
admin.vm.List + $QIXOS_ADMIN_NAME dom0 allow
admin.vm.tag.Get +created-by-$QIXOS_ADMIN_NAME $QIXOS_ADMIN_NAME dom0 allow target=dom0

# Allow read access to some sys-net properties
admin.vm.List + $QIXOS_ADMIN_NAME sys-net allow
admin.vm.tag.Get +created-by-$QIXOS_ADMIN_NAME $QIXOS_ADMIN_NAME sys-net allow target=dom0
admin.vm.property.Get +provides_network $QIXOS_ADMIN_NAME sys-net allow target=dom0

# Allow Remove and List access to VMs managed by qixos
admin.vm.Remove + $QIXOS_ADMIN_NAME @tag:created-by-$QIXOS_ADMIN_NAME allow target=dom0
admin.vm.List + $QIXOS_ADMIN_NAME @tag:created-by-$QIXOS_ADMIN_NAME allow target=dom0

# Allow access to internal qixos.Switch API to manage nix qubes
qixos.Switch * $QIXOS_ADMIN_NAME @tag:created-by-$QIXOS_ADMIN_NAME allow user=root"

# Must run this script as root. There is not a security distinction between root and user in dom0.
if [ "$(id -u)" != "0" ]; then
  echo "This script must be run as root"
  exit 1
fi

# Allow callers to decide which step to run up to
# Call with `./install.sh 4` to run steps 1-4.
# Omit the argument to run all steps
MAX_STEP="${1:-999}"
should_run() {
  local step_num="$1"
  local step_file="$2"
  if [ "$step_num" -gt "$MAX_STEP" ]; then
    echo "Stopped after step $((step_num - 1))"
    exit 0
  fi

  [ ! -f "$step_file" ]
}

mkdir -p "$COMPLETED_INSTALL_STEPS_DIR"

STEP_1="$COMPLETED_INSTALL_STEPS_DIR/STEP_1_COMPLETE"
if should_run 1 "$STEP_1"; then
  echo "STEP 1: Creating $NIX_BUILD_QUBE_NAME and $NIX_INSTALL_QUBE_NAME based on $INSTALLATION_VMS_TEMPLATE"
  
  echo "qvm-create $NIX_BUILD_QUBE_NAME --label red --template $INSTALLATION_VMS_TEMPLATE --class StandaloneVM"
  qvm-create "$NIX_BUILD_QUBE_NAME" --label red --template "$INSTALLATION_VMS_TEMPLATE" --class "StandaloneVM"
  echo "qvm-start $NIX_BUILD_QUBE_NAME"
  qvm-start "$NIX_BUILD_QUBE_NAME"
  # We give this VM 30 GB in order to build the template. More than enough, but we will delete it at the end of
  # the installation anyway
  echo "qvm-volume resize $NIX_BUILD_QUBE_NAME:root $((30 * 1024 * 1024 * 1024))"
  qvm-volume resize "$NIX_BUILD_QUBE_NAME":root $((30 * 1024 * 1024 * 1024))

  echo "qvm-create $NIX_INSTALL_QUBE_NAME --label red --template $INSTALLATION_VMS_TEMPLATE --class StandaloneVM"
  qvm-create "$NIX_INSTALL_QUBE_NAME" --label red --template "$INSTALLATION_VMS_TEMPLATE" --class "StandaloneVM"
  
  touch $STEP_1
fi

STEP_2="$COMPLETED_INSTALL_STEPS_DIR/STEP_2_COMPLETE"
if should_run 2 "$STEP_2"; then
  trap 'echo "Caught interrupt, exiting"; exit 130 &>2' INT TERM
  echo "STEP 2: Installing nix in $NIX_BUILD_QUBE_NAME"
  
  echo "Installing nix in $NIX_BUILD_QUBE_NAME then building qubes nixos template .rpm file. This may take up to 60 minutes."
  qvm-run -p "$NIX_BUILD_QUBE_NAME" "sh <(curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install) --no-daemon && . /home/user/.nix-profile/etc/profile.d/nix.sh && nix --extra-experimental-features nix-command --extra-experimental-features flakes --option system-features 'kvm benchmark big-parallel nixos-test' build --no-write-lock-file 'git+https://github.com/originalposter/qixos?ref=master&dir=install/build-nix-template'#rpm"
  
  trap - INT TERM
  touch "$STEP_2"
fi

STEP_3="$COMPLETED_INSTALL_STEPS_DIR/STEP_3_COMPLETE"
if should_run 3 "$STEP_3"; then
  echo "STEP 3: Copying .rpm from $NIX_BUILD_QUBE_NAME to $NIX_INSTALL_QUBE_NAME"

  echo "Please approve the copy and send it to $NIX_INSTALL_QUBE_NAME"
  qvm-run "$NIX_BUILD_QUBE_NAME" "qvm-copy-to-vm $NIX_INSTALL_QUBE_NAME /home/user/result/*.rpm"

  touch "$STEP_3"
fi

STEP_4="$COMPLETED_INSTALL_STEPS_DIR/STEP_4_COMPLETE"
if should_run 4 "$STEP_4"; then
  echo "STEP 4: Installing qubes-core-admin-client in order to get qvm-template on $NIX_INSTALL_QUBE_NAME"

  echo "qvm-run -p $NIX_INSTALL_QUBE_NAME sudo dnf install -y qubes-core-admin-client"
  qvm-run -p "$NIX_INSTALL_QUBE_NAME" "sudo dnf install -y qubes-core-admin-client"

  touch "$STEP_4"
fi

STEP_5="$COMPLETED_INSTALL_STEPS_DIR/STEP_5_COMPLETE"

# Variables should be defined outside of the if in order to be available later
TEMPORARY_INSTALL_POLICY_FILE_PATH="/etc/qubes/policy.d/1-qixos-temporary-install.policy"

# We can't configure this. It is set by the .rpm
NIXOS_TEMPLATE="nixos"

# This step is large because we don't want to leave policy files in case of qvm-template install failure
if should_run 5 "$STEP_5"; then
  # In case this step errors out we want to make sure we remove the policy files
  # For that reason we disable exit on error for this step
  set +e
  echo "STEP 5.a: Creating temporary policies that allow qvm-template to be ran inside $NIX_INSTALL_QUBE_NAME"

  echo "Creating temporary policy at $TEMPORARY_INSTALL_POLICY_FILE_PATH"
  cat > "$TEMPORARY_INSTALL_POLICY_FILE_PATH" << EOF
admin.vm.Create.TemplateVM + $NIX_INSTALL_QUBE_NAME dom0 allow target=dom0
admin.vm.List + $NIX_INSTALL_QUBE_NAME dom0 allow target=dom0
admin.property.Get +updatevm $NIX_INSTALL_QUBE_NAME dom0 allow target=dom0
admin.Events + $NIX_INSTALL_QUBE_NAME dom0 allow target=dom0

admin.vm.List + $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.volume.List + $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.volume.ImportWithSize +root $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.Start + $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.Shutdown + $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.CurrentState + $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.property.Set * $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.feature.Set * $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.feature.Remove * $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0
admin.vm.property.Reset * $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow target=dom0

qubes.PostInstall + $NIX_INSTALL_QUBE_NAME $NIXOS_TEMPLATE allow
EOF
  
  echo "STEP 5.b: Installing the $NIXOS_TEMPLATE template using qvm-template install"

  echo "qvm-run -p $NIX_INSTALL_QUBE_NAME qvm-template install /home/user/QubesIncoming/$NIX_BUILD_QUBE_NAME/*.rpm --nogpgcheck"
  qvm-run -p "$NIX_INSTALL_QUBE_NAME" "qvm-template install /home/user/QubesIncoming/$NIX_BUILD_QUBE_NAME/*.rpm --nogpgcheck"
  ERROR=$?

  echo "STEP 5.c: Removing the temporary policy files"

  echo "rm $TEMPORARY_INSTALL_POLICY_FILE_PATH"
  rm "$TEMPORARY_INSTALL_POLICY_FILE_PATH"

  # Need to exit in case the qvm-template call failed
  if [ $ERROR != 0 ]; then
    qvm-remove --force $NIXOS_TEMPLATE
    exit $ERROR
  fi

  # Re-enable exit on error
  set -e
  touch "$STEP_5"
fi

STEP_6="$COMPLETED_INSTALL_STEPS_DIR/STEP_6_COMPLETE"
if should_run 6 "$STEP_6"; then
  echo "STEP 6: Removing $NIX_INSTALL_QUBE_NAME and $NIX_BUILD_QUBE_NAME"

  qvm-shutdown --wait "$NIX_INSTALL_QUBE_NAME"
  qvm-shutdown --wait "$NIX_BUILD_QUBE_NAME"
  echo "qvm-remove --force $NIX_INSTALL_QUBE_NAME"
  qvm-remove --force "$NIX_INSTALL_QUBE_NAME"
  echo "qvm-remove --force $NIX_BUILD_QUBE_NAME"
  qvm-remove --force "$NIX_BUILD_QUBE_NAME"

  touch "$STEP_6"
fi

STEP_7="$COMPLETED_INSTALL_STEPS_DIR/STEP_7_COMPLETE-$QIXOS_ADMIN_NAME"
if should_run 7 "$STEP_7"; then
  echo "STEP 7: Create TemplateVM $QIXOS_BASE_TEMPLATE from $NIXOS_TEMPLATE"

  # Create qixos base template from nixos
  echo "qvm-clone $NIXOS_TEMPLATE $QIXOS_BASE_TEMPLATE"
  qvm-clone "$NIXOS_TEMPLATE" "$QIXOS_BASE_TEMPLATE"

  touch "$STEP_7"
fi

STEP_8="$COMPLETED_INSTALL_STEPS_DIR/STEP_8_COMPLETE-$QIXOS_ADMIN_NAME"
if should_run 8 "$STEP_8"; then
  echo "STEP 8: Resizing $QIXOS_BASE_TEMPLATE filesystem"

  # TODO: Need to fix and package `/usr/lib/qubes/resize-rootfs` in nix template
  # HACK: We can get arround this causing an error by shutting down the template before resizing
  echo "qvm-shutdown --wait $QIXOS_BASE_TEMPLATE"
  qvm-shutdown --wait "$QIXOS_BASE_TEMPLATE"
  echo "qvm-volume resize $QIXOS_BASE_TEMPLATE:root $((30 * 1024 * 1024* 1024))"
  qvm-volume resize "$QIXOS_BASE_TEMPLATE":root $((30 * 1024 * 1024* 1024))

  touch "$STEP_8"
fi

STEP_9="$COMPLETED_INSTALL_STEPS_DIR/STEP_9_COMPLETE-$QIXOS_ADMIN_NAME"
if should_run 9 "$STEP_9"; then
  echo "STEP 9: nixos-rebuild $QIXOS_BASE_TEMPLATE to install the nix basics"

  # Need to set proxy setting to have internet access in template
  echo "qvm-run -p -u root $QIXOS_BASE_TEMPLATE 'all_proxy=127.0.0.1:8082 nixos-rebuild boot --flake /etc/nixos#nixos'"
  qvm-run -p -u root "$QIXOS_BASE_TEMPLATE" "all_proxy=127.0.0.1:8082 nixos-rebuild boot --flake /etc/nixos#nixos"

  echo "qvm-shutdown --wait $QIXOS_BASE_TEMPLATE"
  qvm-shutdown --wait "$QIXOS_BASE_TEMPLATE"

  touch "$STEP_9"
fi

STEP_10="$COMPLETED_INSTALL_STEPS_DIR/STEP_10_COMPLETE-$QIXOS_ADMIN_NAME"
if should_run 10 "$STEP_10"; then
  echo "STEP 10: Running nixos-rebuild boot on $QIXOS_BASE_TEMPLATE to the admin flake at $QIXOS_ADMIN_FLAKE"

  echo "qvm-run -p -u root $QIXOS_BASE_TEMPLATE 'all_proxy=127.0.0.1:8082 nixos-rebuild boot --flake $QIXOS_ADMIN_FLAKE --no-write-lock-file --refresh'"
  qvm-run -p -u root "$QIXOS_BASE_TEMPLATE" "all_proxy=127.0.0.1:8082 nixos-rebuild boot --flake $QIXOS_ADMIN_FLAKE --no-write-lock-file --refresh"

  echo "nix-collect-garbage"
  qvm-run -p -u root "$QIXOS_BASE_TEMPLATE" "nix-collect-garbage"

  echo "qvm-shutdown --wait $QIXOS_BASE_TEMPLATE"
  qvm-shutdown --wait "$QIXOS_BASE_TEMPLATE"

  touch "$STEP_10"
fi

STEP_11="$COMPLETED_INSTALL_STEPS_DIR/STEP_11-$QIXOS_ADMIN_NAME"
if should_run 11 "$STEP_11"; then
  echo "STEP 11: Creating $QIXOS_ADMIN_NAME from $QIXOS_BASE_TEMPLATE"

  # Create qixos admin qube from the base template
  echo "qvm-create $QIXOS_ADMIN_NAME -t $QIXOS_BASE_TEMPLATE --label black --standalone"
  qvm-create "$QIXOS_ADMIN_NAME" -t "$QIXOS_BASE_TEMPLATE" --label black --standalone

  touch "$STEP_11"
fi

STEP_12="$COMPLETED_INSTALL_STEPS_DIR/STEP_12-$QIXOS_ADMIN_NAME"
if should_run 12 "$STEP_12"; then
  echo "STEP 12: Creating $QIXOS_ADMIN_NAME policy file at $QIXOS_ADMIN_POLICY_FILE"

  echo "Creating policy file at $QIXOS_ADMIN_POLICY_FILE"

  printf '%s\n' "$QIXOS_ADMIN_POLICY" > "$QIXOS_ADMIN_POLICY_FILE"

  INCLUDE_ADMIN_LOCAL_RWX_POLICY="$QIXOS_ADMIN_NAME @tag:created-by-$QIXOS_ADMIN_NAME allow target=dom0"
  INCLUDE_ADMIN_LOCAL_RWX_FILE="/etc/qubes/policy.d/include/admin-local-rwx"
  if ! grep -qF "$INCLUDE_ADMIN_LOCAL_RWX_POLICY" "$INCLUDE_ADMIN_LOCAL_RWX_FILE"; then
    echo "Adding $INCLUDE_ADMIN_LOCAL_RWX_POLICY to $INCLUDE_ADMIN_LOCAL_RWX_FILE"
    echo "$INCLUDE_ADMIN_LOCAL_RWX_POLICY" >> "$INCLUDE_ADMIN_LOCAL_RWX_FILE"
  fi

  touch "$STEP_12"
fi

STEP_13="$COMPLETED_INSTALL_STEPS_DIR/STEP_13-$QIXOS_ADMIN_NAME"
if should_run 13 "$STEP_13"; then
  echo "STEP 13: Adding 'created-by-$QIXOS_ADMIN_NAME' tag to $QIXOS_ADMIN_NAME and $QIXOS_BASE_TEMPLATE"

  echo "qvm-tags $QIXOS_ADMIN_NAME add created-by-$QIXOS_ADMIN_NAME"
  qvm-tags "$QIXOS_ADMIN_NAME" add "created-by-$QIXOS_ADMIN_NAME"

  echo "qvm-tags $QIXOS_BASE_TEMPLATE add created-by-$QIXOS_ADMIN_NAME"
  qvm-tags "$QIXOS_BASE_TEMPLATE" add "created-by-$QIXOS_ADMIN_NAME"

  touch "$STEP_13"
fi

echo "DONE! qixos has been installed! You may start $QIXOS_ADMIN_NAME and use qixos-rebuild"
