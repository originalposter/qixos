{
  nixos-rebuild,
  python3Packages,
  qubes-core-admin-client ? null
}:
let
  base = python3Packages.buildPythonPackage {
    pname = "qixos-rebuild";
    version = "0.1.0";
    src = ./.;
    propagatedBuildInputs = [ python3Packages.pydantic ];
    pyproject = true;
    build-system = [ python3Packages.hatchling ];
    nativeCheckInputs = [ python3Packages.flake8 ];
    checkPhase = ''
      flake8 --ignore E501,W503 src/
    '';
    postFixup = ''
      wrapProgram $out/bin/qixos-switch \
        --prefix PATH : ${nixos-rebuild}/bin
    '';
  };
in
{
  # Basic build that only builds the qixos.Switch script
  qixosSwitch = base;

  # Same code-base and build system as qixos.Switch but needs admin dependency for qixos-rebuild
  qixosRebuild = base.overrideAttrs (old: {
    pname = "qixos-rebuild";
    propagatedBuildInputs = old.propagatedBuildInputs ++ [ qubes-core-admin-client ];
  });
}
