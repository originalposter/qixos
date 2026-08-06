# `bootstrap-systemd-activation` function
#
# BEWARE there be serpents here
# This function returns a module that has 1 responsibility:
# Create two oneshot systemd jobs that in the TemplateVM does nothing
# and in the AppVMs they switch over to the appropriate AppVM derivation.
#
# An important function of this model is that it allows
# AppVMs to have their own specific root filesystem configurations.
#
# The functional purpuse of this module is to allow an AppVM to boot into
# its alread-built configuration from the TemplateVM.
# This functionality does NOT have to be implemented as a systemd job but
# as of the writing this was the simplest way to make it happen.
# This functionality may be changed in the future to be implemented some other way
# for example as based on kernel boot or initd.
# The way it works currently pushes systemd and nix to their limits and the constraints
# and quirks of this system are many.
#
# NOTE serpent I: It is important that the activation is completed.
# It is somewhat easy to build this in a way where the systemd job
# that is running the activation script is killed by the activation script
# since the activation script kills systemd jobs.
# For that reason it is important that this systemd job
# is undisturbed as an activation is going.
# One way to make sure that happens is by avoiding being killed by the activation script.
# One way to avoid that is by not changing when going from one derivation to the other.
#
# NOTE Serpent II: it is difficult to naively have the final AppVM derivation include this job
# because we would normally run the "/nix/store/<hash1>/stuff.config.system.build.toplevel/activate"
# script but if that build includes a systemd job that has "/nix/store/<hash2>/stuff.config.system.build.toplevel/activate"
# in it one could not put in hash1 as hash2 since hash1 depends on hashing the file that includes hash2.
# So one would have to create a derivation for hash2, but that would require hash3, etc...
#
# Serpent II might make one reach for skipping the below job in the AppVM activation
# However, not only would this be a hack, but serpent I makes this a very bad solution since
# it leads the activation script to kill itself and therebye borking the system in a half-activated state.
#
# Instead the solution is to have the systemd job point to a runtime location for the activation script
#
# NOTE Serpent III: It is a quirk of nixOS's `switch-to-configuration` script that
# it will iterate over currently-active units when deciding which to restart.
# In our systemd job that makes the AppVM switch we make use of `switch-to-configuration`
# but we encounter a problem when the new AppVM configuration contains systemd jobs that are
# not defined in the old TemplateVM configuration AND start later in the systemd boot chain than
# the qixos switch runs. This causes the `switch-to-configuration` to ignore the new job and to not start it.
# The fix for this is to run our qixos switch job as late as possible so that all jobs in the new configuration
# will have been activated and will be noticed.
# The way this is enforced is by running our qixos switch job `after = [ "default.target" ]` meaning all jobs
# that are `wantedBy = [ "default.target" ]` or `multi-user.target` or `basic.target` will be active by that point.
# ASSUMPTION: no normal systemd jobs are wantedBy a target later than "default.target" if that's the case then
# that job may not be started by qixos switch and we should try to run this qixos switch job even later.
#
# NOTE Serpent IV: Restarting the systemd daemon in the wrong way can cause core qubes daemons like the qubes GUI daemon
# which causes the VM to not be reachable by any GUI application. For this reason care should be taken to not restart
# systemd once the GUI daemon has started.
#
# NOTE Serpent V: `switch-to-configuration` does reload the user systemd manager, but only
# partially. It re-execs it (so new unit files under /etc/systemd/user are read) and restarts
# `nixos-activation.service`, but a re-exec does not pull in newly wanted units. Any
# `systemd.user.services` that exists in the AppVM configuration but not in the template's would
# therefore sit dormant until the next boot.
# Starting the user's `default.target` fixes that: systemd re-evaluates the target's `Wants=` and
# pulls in anything newly present that isn't running. This is the same trick
# `switch-to-configuration` relies on for system targets, described in the note on the system
# service below, applied one level down in the user manager.
# We do it inline at the tail of this job rather than from a second job running in the user
# manager, because ordering between a system job and a user job cannot be expressed in systemd -
# `before = [ "user@1000.service" ]` says nothing once that unit is already running, and the user
# manager reaches its own `default.target` long before the system reaches ours. Sequential lines in
# one script are actually ordered.
# Reaching the user manager from root needs nothing but XDG_RUNTIME_DIR, which is how
# `switch-to-configuration` and home-manager both do it. If no session is open yet the call simply
# fails and is ignored - `default.target` will then start normally when the session does open, and
# pick everything up anyway.
{ appVmNames, activationDir, runQixosDir }: { pkgs, ... }:
let
  nixosActivationCall = name: "${activationDir}/${name}/nixos/bin/switch-to-configuration test";
  alreadyActivatedPath = "${runQixosDir}/already-activated";

  activationScript = pkgs.writeShellScript "qixos-appvm-switch" ''
    set -euo pipefail
    # Make sure we have not already run this
    if [ -f ${alreadyActivatedPath} ]; then exit 0; fi
    mkdir -p ${runQixosDir}
    touch ${alreadyActivatedPath}

    # Starts the user's default.target so that user units which the AppVM configuration adds
    # on top of the template's get picked up. See NOTE Serpent V.
    # `--init-groups` is what su(1) and runuser(1) do; setpriv refuses to change the gid
    # without being told how to handle supplementary groups, and keeping root's would leak
    # them into the user's process.
    start_user_default_target() {
      local user uid gid
      user=$(${pkgs.qubes-core-qubesdb}/bin/qubesdb-read /default-user || echo user)
      uid=$(${pkgs.coreutils}/bin/id -u "$user")
      gid=$(${pkgs.coreutils}/bin/id -g "$user")
      ${pkgs.util-linux}/bin/setpriv --reuid="$uid" --regid="$gid" --init-groups \
        env XDG_RUNTIME_DIR="/run/user/$uid" \
        ${pkgs.systemd}/bin/systemctl --user start default.target || true
    }

    QUBE_NAME=$(${pkgs.qubes-core-qubesdb}/bin/qubesdb-read /name)
    case "$QUBE_NAME" in
      ${builtins.concatStringsSep "\n      " (
          map (name: ''
            ${name})
              ${nixosActivationCall name}
              start_user_default_target
              ;;
          '') appVmNames
      )}
      *) echo "No qixos config for qube: $QUBE_NAME"; exit 1 ;;
    esac
  '';
in
{
  systemd.services.qixos-appvm-switch = {
    description = "switch to the App VM nix configuration on the system level";

    # Run after default.target so that ALL targets are active when 
    # switch-to-configuration runs. switch-to-configuration iterates over
    # currently-active units; for each active target it sees, it issues a
    # start_unit call which causes systemd to re-evaluate that target's wants
    # and pull in any newly-installed units.
    # Targets that aren't active when s-t-c  starts are invisible to it,
    # and units wantedBy those not-yet-active targets are silently ignored. 
    #
    # This means: any unit in the AppVM config that's wantedBy a target 
    # activated LATER than default.target won't be started by s-t-c. We 
    # assume no such targets exist on a normal system. If you add a custom 
    # target that activates after default.target and have units wantedBy 
    # it, we'll need to revisit this.
    #
    # Run before user@1000.service so that the switch has preferably happened before the
    # user session starts. This is only a preference: the session is usually already up by
    # the time we run, which is exactly why the user side of the switch is done inline at
    # the end of the activation script rather than from a second unit. See NOTE Serpent V.
    after = [ "qubes-db.service" "default.target" ];
    before = [ "user@1000.service" ];
    requires = [ "qubes-db.service" ];
    wantedBy = [ "default.target" ];

    path = with pkgs; [ nix coreutils findutils gnused util-linux ];

    environment = {
      HOME = "/home/user";
      NIX_PATH = "nixpkgs=${pkgs.path}";
    };

    serviceConfig = {
      Type = "oneshot";
      User = "root";
      ExecStart = activationScript;
      RemainAfterExit = true;
    };

    # Only run if we're an AppVM, not a TemplateVM
    unitConfig = {
      ConditionPathExists = "!/run/qubes/this-is-templatevm";
    };
  };
}
