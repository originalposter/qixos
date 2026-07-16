# Returns core qix modules that ought to be imported by home manager
[ ({ lib, ...}: {
  home.activation.linkDesktopFiles = lib.hm.dag.entryAfter ["installPackages"] ''
    mkdir -p $HOME/.local/share/applications
    rm -f $HOME/.local/share/applications/*.desktop
    ln -sf $HOME/.nix-profile/share/applications/*.desktop \
    $HOME/.local/share/applications/
  '';
  home.stateVersion = "24.05";
  home.username = "user";
  home.homeDirectory = "/home/user";
}) ]
