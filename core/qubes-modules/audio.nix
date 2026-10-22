# Copyright (C) 2026 op (op@qixos.org)
# The pipewire.service drop-in follows appvm-scripts/lib/systemd/user/pipewire.service.d
# in https://github.com/QubesOS/qubes-gui-agent-linux
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Audio for nubes: PipeWire in the user's session, with Qubes' module carrying playback
# to the audio qube over vchan and recording back from it. Which qube that is, and
# whether a microphone is attached at all, is dom0's decision.
#
# On wherever the gui agent is, as on a stock Qubes template.
{
  config,
  lib,
  pkgs,
  ...
}: let
  # Built against the daemon that will load it.
  module = pkgs.qubes-pipewire-module.override {pipewire = config.services.pipewire.package;};
in {
  options.services.qubes.audio.enable =
    lib.mkEnableOption "audio through the qubes audio VM"
    // {
      default = config.services.qubes.gui.enable;
      defaultText = lib.literalExpression "config.services.qubes.gui.enable";
    };

  config = lib.mkIf config.services.qubes.audio.enable {
    services.pipewire = {
      enable = true;
      # Most applications still speak PulseAudio or ALSA rather than PipeWire.
      pulse.enable = true;
      alsa.enable = true;
      configPackages = [module];
    };

    # PipeWire looks for modules in one directory unless told otherwise, and the qubes
    # one is in a store path of its own.
    systemd.user.services.pipewire = {
      environment.PIPEWIRE_MODULE_DIR = "${config.services.pipewire.package}/lib/pipewire-0.3:${module}/lib/pipewire-0.3";
      # A root session's pipewire would take the vchan to the audio qube from the user's.
      unitConfig.ConditionUser = "!root";
    };
  };
}
