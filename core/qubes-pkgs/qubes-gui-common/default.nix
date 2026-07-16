{
  lib,
  stdenv,
  fetchFromGitHub,
}:
stdenv.mkDerivation rec {
  pname = "qubes-gui-common";
  version = "4.3.1";

  src = fetchFromGitHub {
    owner = "QubesOS";
    repo = pname;
    rev = "v${version}";
    hash = "sha256-RDB2tS+vLXu7RwA6Ng4TekIubzIKtuQK8ALRGjsXmcY=";
  };

  buildPhase = ''
    true
  '';

  installPhase = ''
    mkdir -p $out/include
    cp include/*.h $out/include/
  '';

  meta = with lib; {
    description = "Common files for Qubes GUI - protocol headers";
    homepage = "https://qubes-os.org";
    license = licenses.gpl2Plus;
    maintainers = [];
    platforms = platforms.linux;
  };
}
