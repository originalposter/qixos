# Copyright (C) 2026 op (op@qixos.org)
# Derived from the pipewire/ directory of https://github.com/QubesOS/qubes-gui-agent-linux
# SPDX-License-Identifier: GPL-2.0-or-later
#
# `unresholved` because resholve wraps the gui agent, and the wrapper's own `src` is the
# unwrapped build rather than the source.
{
  stdenv,
  pkg-config,
  pipewire,
  qubes-core-qubesdb,
  qubes-core-vchan-xen,
  qubes-gui-agent-linux,
  xen,
}:
stdenv.mkDerivation {
  pname = "qubes-pipewire-module";
  inherit (qubes-gui-agent-linux) version;
  inherit (qubes-gui-agent-linux.unresholved) src;

  nativeBuildInputs = [pkg-config];
  buildInputs = [pipewire qubes-core-qubesdb qubes-core-vchan-xen xen];

  buildPhase = ''
    make -C pipewire qubes-pw-module.so
  '';

  installPhase = ''
    install -Dm755 pipewire/qubes-pw-module.so $out/lib/pipewire-0.3/libpipewire-module-qubes.so
    install -Dm644 pipewire/30_qubes.conf $out/share/pipewire/pipewire.conf.d/30_qubes.conf
  '';
}
