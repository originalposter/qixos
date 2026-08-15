# This function returns a module.
# This module will at activation time link the `appVmDerivations` activation directories.
# `appVmDerivations` is a attrs which maps appVmNames to those appVMs' nixos configurations.
# This module will create a symlink to each configuration's top level directory under
# activationDir/appVmName/nixos
# where activationDir = /run/qixos/activation; in practice (code is SoT)
{ appVmDerivations, activationDir }: { self, pkgs, lib, ... }:
{
  system.activationScripts.linkAppVmConfigs = ''
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: drv:
      lib.concatStringsSep "\n" [
        "mkdir -p ${activationDir}/${name}"
        "ln -sfn ${drv.config.system.build.toplevel} ${activationDir}/${name}/nixos"
      ]
      ) appVmDerivations)}
  '';
}
