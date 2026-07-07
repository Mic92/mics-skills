{
  lib,
  buildPythonApplication,
  hatchling,
  makeWrapper,
  pytestCheckHook,
  grim,
  stdenv,
}:

# spectacle, swaymsg and niri ship with the desktop/compositor, so they are
# left off PATH to avoid dragging KDE (spectacle -> qtbase/kio/kservice) onto
# everyone. grim is standalone and may be missing, so it stays bundled.
buildPythonApplication {
  pname = "screenshot-cli";
  version = "0.1.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  nativeCheckInputs = [ pytestCheckHook ];

  nativeBuildInputs = lib.optional stdenv.hostPlatform.isLinux makeWrapper;

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/screenshot-cli
  ''
  + lib.optionalString stdenv.hostPlatform.isLinux ''
    wrapProgram $out/bin/screenshot-cli --prefix PATH : ${lib.makeBinPath [ grim ]}
  '';

  meta = {
    description = "Cross-platform screenshot CLI for macOS and KDE Wayland";
    mainProgram = "screenshot-cli";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux ++ lib.platforms.darwin;
  };
}
