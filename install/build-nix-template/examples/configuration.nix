{
  config,
  lib,
  pkgs,
  ...
}: {
  nix = {
    settings = {
      experimental-features = ["nix-command" "flakes"];
    };
  };

  hardware.graphics.enable = true;

  environment.systemPackages = with pkgs; [
    xterm
    git
  ];

  # We need to make sure stateVersion is 26.05 at all stages of the installation
  system.stateVersion = "26.05";
}
