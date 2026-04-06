{
  lib,
  buildPythonApplication,
  hatchling,
  makeWrapper,
  pytestCheckHook,
  # Linux-only screenshot backends, null on non-Linux
  grim ? null,
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
      spectacle
      # sway gives us swaymsg for window-geometry queries on sway sessions;
      # niri uses its own IPC and isn't bundled because it's the running
      # compositor.
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

  nativeCheckInputs = [ pytestCheckHook ];

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
