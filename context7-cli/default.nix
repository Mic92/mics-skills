{
  lib,
  buildPythonApplication,
  hatchling,
}:

buildPythonApplication {
  pname = "context7-cli";
  version = "0.1.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  dependencies = [ ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/context7-cli
  '';

  meta = {
    description = "CLI for Context7 library documentation API";
    mainProgram = "context7-cli";
    license = lib.licenses.mit;
    maintainers = [ ];
  };
}
