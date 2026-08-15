# Makes the nube's installed applications visible to dom0's appmenus.
#
# dom0 discovers a qube's applications over the `qubes.GetAppmenus` qrexec service
# from qubes-core-agent-linux, which only reads `.desktop` files from directories
# that survive a VM restart:
#
#   persistence=$(qubesdb-read /qubes-vm-persistence || echo full)
#   ...
#   elif [ "$persistence" = "rw-only" ] && \
#           [ "$(stat -c %D "$dir")" = "$rw_devno" ]; then
#
# In an AppVM persistence is `rw-only`, so only directories on `/rw` count.
# `/run/current-system/sw/share/applications` and the rest of XDG_DATA_DIRS live on
# the root volume and are silently skipped, leaving `~/.local/share/applications` as
# the only path that qualifies. An AppVM therefore shows no applications at all
# unless its `.desktop` files are linked into the home directory. Templates and
# standalones have `full` persistence and would work without this; we link there
# anyway so every nube behaves the same.
#
# We link from every profile a nube might install applications into rather than
# assuming a particular tool put them there: the system profile, the per-user
# profile (home-manager with `useUserPackages`), and the user's nix profile
# (home-manager without it, or `nix-env`). Later sources win.
{
  config,
  lib,
  pkgs,
  ...
}:
with lib; {
  options.services.qubes.appmenus.enable =
    mkEnableOption "linking .desktop files where dom0's appmenus can find them";

  config = mkIf config.services.qubes.appmenus.enable {
    systemd.user.services.qubes-link-desktop-files = {
      description = "link .desktop files into the home directory for qubes appmenus";
      # Starting default.target again is also how an AppVM switch re-runs this.
      wantedBy = ["default.target"];

      path = with pkgs; [coreutils findutils];

      script = ''
        set -eu

        target="$HOME/.local/share/applications"
        mkdir -p "$target"

        # Only drop symlinks, which are the only thing we create. A .desktop file
        # the user wrote by hand is a regular file and is left alone.
        find "$target" -maxdepth 1 -name '*.desktop' -type l -delete

        for dir in \
          /run/current-system/sw/share/applications \
          "/etc/profiles/per-user/$(id -un)/share/applications" \
          "$HOME/.nix-profile/share/applications"
        do
          [ -d "$dir" ] || continue
          for desktop in "$dir"/*.desktop; do
            [ -e "$desktop" ] || continue
            ln -sfn "$desktop" "$target/$(basename "$desktop")"
          done
        done
      '';

      serviceConfig = {
        Type = "oneshot";
        # Deliberately no RemainAfterExit. An AppVM runs this once under the
        # template's configuration, then the qixos switch starts the user's
        # default.target again to repopulate from the AppVM's own profiles. A
        # oneshot only re-runs if it fell back to inactive, so RemainAfterExit
        # would leave the AppVM showing the template's applications.
      };
    };
  };
}
