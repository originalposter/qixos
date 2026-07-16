# This function returns a module.
# This module will at activation time link the `appVmDerivations` activation directories.
# `appVmDerivations` is a attrs which maps appVmNames to paths to the activation and top level directories
# for those appVMs' HM and nixos derivations respectively.
# This module will create a symlink to those activation paths under the directory
# activationDir/appVmName/lnixos or hm)
# where activationDir = /run/qixos/activation; in practice (code is SoT)
{ appVmDerivations, activationDir }: { self, pkgs, lib, ... }:
{
  system.activationScripts.linkAppVmConfigs = ''
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: drv:
      lib.concatStringsSep "\n" [
        "mkdir -p ${activationDir}/${name}"
        "ln -sfn ${drv.root.config.system.build.toplevel} ${activationDir}/${name}/nixos"
        "ln -sfn ${drv.home.activationPackage} ${activationDir}/${name}/hm"
      ]
      ) appVmDerivations)}
  '';
}
