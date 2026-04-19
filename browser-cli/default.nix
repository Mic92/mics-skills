{
  buildPythonApplication,
  hatchling,
  websockets,
  browsh,
  makeWrapper,
}:

buildPythonApplication {
  pname = "browser-cli";
  version = "0.4.0";
  src = ./.;
  pyproject = true;

  build-system = [ hatchling ];

  nativeBuildInputs = [ makeWrapper ];

  dependencies = [ websockets ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/browser-cli
  '';

  postFixup = ''
    wrapProgram $out/bin/browser-cli \
      --prefix PATH : ${browsh}/bin
  '';

  meta = {
    description = "Control Firefox browser from the command line";
    mainProgram = "browser-cli";
  };
}
