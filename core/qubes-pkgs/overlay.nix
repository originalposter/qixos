# The qubes packages every nube needs, plus qixos-switch, which core's modules reach for
# through `pkgs` when they install the qixos.Switch endpoint.
#
# A file rather than a list inside the flake, for the reason ../qubes-modules/default.nix
# gives: install/build-nix-template needs the same set.
#
# `final` rather than `prev`, so these can depend on each other through the overlay.
final: _prev: {
  qubes-core-vchan-xen = final.callPackage ./qubes-core-vchan-xen {};
  qubes-core-qubesdb = final.callPackage ./qubes-core-qubesdb {};
  qubes-core-agent-linux = final.callPackage ./qubes-core-agent-linux {};
  qubes-core-qrexec = final.callPackage ./qubes-core-qrexec {};
  qubes-gui-agent-linux = final.callPackage ./qubes-gui-agent-linux {};
  qubes-gui-common = final.callPackage ./qubes-gui-common {};
  qubes-linux-utils = final.callPackage ./qubes-linux-utils {};
  qubes-usb-proxy = final.callPackage ./qubes-usb-proxy {};
  qixos-switch = (final.callPackage ../qixos-rebuild {}).qixosSwitch;
}
