{
  lib,
  buildPythonApplication,
  hatchling,
  makeWrapper,
  # Linux-only screenshot backends, null on non-Linux
  grim ? null,
  slurp ? null,
  spectacle ? null,
  sway ? null,
  jq,
  stdenv,
}:

let
  isLinux = stdenv.hostPlatform.isLinux;
  runtimeDeps = lib.optionals isLinux (
    lib.filter (p: p != null) [
      grim
      slurp
      spectacle
      sway
      jq
    ]
  );
in

buildPythonApplication {
  pname = "screenshot-cli";
  version = "0.1.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  nativeBuildInputs = [ makeWrapper ];

  postInstall = lib.optionalString (runtimeDeps != [ ]) ''
    wrapProgram $out/bin/screenshot-cli \
      --prefix PATH : ${lib.makeBinPath runtimeDeps}
  '';

  meta = {
    description = "Cross-platform screenshot CLI for macOS and KDE Wayland";
    mainProgram = "screenshot-cli";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux ++ lib.platforms.darwin;
  };
}
