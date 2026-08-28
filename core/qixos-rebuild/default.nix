{
  nixos-rebuild,
  python3Packages,
  qubes-core-admin-client ? null
}:
let
  # One builder for both variants rather than an overrideAttrs of one by the other.
  # buildPythonPackage rewrites `checkPhase` into `installCheckPhase` from the attrs it is
  # given, which happens before any override, so a checkPhase added by overrideAttrs is
  # carried on the derivation and never run.
  mkQixosRebuild = {
    pname,
    extraDeps ? [ ],
    extraCheckInputs ? [ ],
    extraChecks ? "",
  }: python3Packages.buildPythonPackage {
    inherit pname;
    version = "0.1.0";
    src = ./.;
    propagatedBuildInputs = [ python3Packages.pydantic ] ++ extraDeps;
    pyproject = true;
    build-system = [ python3Packages.hatchling ];
    nativeCheckInputs = [ python3Packages.flake8 ] ++ extraCheckInputs;
    checkPhase = ''
      flake8 --ignore E501,W503 src/ tests/
      ${extraChecks}
    '';
    postFixup = ''
      wrapProgram $out/bin/qixos-switch \
        --prefix PATH : ${nixos-rebuild}/bin
    '';
  };
in
{
  # Basic build that only builds the qixos.Switch script
  qixosSwitch = mkQixosRebuild {
    pname = "qixos-switch";
  };

  # Same code-base and build system as qixos.Switch but needs admin dependency for qixos-rebuild.
  # The pytest suite runs here rather than in the switch build because it covers admin-side
  # code: switch.py imports qubesadmin at module level, which only this variant has.
  qixosRebuild = mkQixosRebuild {
    pname = "qixos-rebuild";
    extraDeps = [ qubes-core-admin-client ];
    extraCheckInputs = [ python3Packages.pytest ];
    extraChecks = "PYTHONPATH=$PWD/src:$PYTHONPATH pytest tests/";
  };
}
