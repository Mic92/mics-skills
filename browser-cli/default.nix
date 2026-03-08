{
  buildPythonApplication,
  hatchling,
  websockets,
  browsh,
  makeWrapper,
}:

buildPythonApplication {
  pname = "browser-cli";
  version = "0.3.0";
  src = ./.;
  pyproject = true;

  build-system = [ hatchling ];

  nativeBuildInputs = [ makeWrapper ];

  dependencies = [ websockets ];

  postFixup = ''
    wrapProgram $out/bin/browser-cli \
      --prefix PATH : ${browsh}/bin
  '';

  meta = {
    description = "Control Firefox browser from the command line";
    mainProgram = "browser-cli";
  };
}
