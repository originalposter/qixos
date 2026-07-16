{
  fetchFromGitHub,
  python3,
  python3Packages,
  makeWrapper,
  stdenv,
  qubes-core-qrexec,
}:

stdenv.mkDerivation rec {
  version = "4.3.30";
  pname = "qubes-core-admin-client";

  src = fetchFromGitHub {
    owner = "QubesOS";
    repo = "qubes-core-admin-client";
    rev = "v${version}";
    hash = "sha256-B3LxCH+sT1ZO9XqTjmFE8jFKF7FcjRhLdbfDrqS7uTo=";
  };

  nativeBuildInputs = [ makeWrapper python3 ] ++ (with python3Packages; [
    setuptools lxml python-daemon pyxdg pyyaml tqdm xcffib
  ]);

  # FIXME: Curious why eVq did not package something called `qrexec-client` but instead symlinked to `qrexec-client-vm`
  # but with that name?
  patchPhase = ''
    substituteInPlace ./setup.py \
      --replace 'os.path.join(self.root, "usr/bin")' 'os.path.join(self.prefix, "bin")' \
      --replace '"""#!/usr/bin/python3' '"""#!${python3}/bin/python3'

    substituteInPlace ./qubesadmin/config.py \
      --replace "QREXEC_CLIENT = '/usr/lib/qubes/qrexec-client'" "QREXEC_CLIENT = '${qubes-core-qrexec}/lib/qubes/qrexec-client-vm'" \
      --replace "QREXEC_CLIENT_VM = '/usr/bin/qrexec-client-vm'" "QREXEC_CLIENT_VM = '${qubes-core-qrexec}/bin/qrexec-client-vm'"
  '';

  buildPhase = ''
    python3 setup.py build
  '';

  installPhase = ''
    python3 setup.py install --prefix=$out
    for f in $out/bin/*; do
      wrapProgram $f \
        --prefix PYTHONPATH : $out/lib/python${python3.pythonVersion}/site-packages
    done
  '';
}
