{
  lib,
  buildPythonApplication,
  hatchling,
}:

buildPythonApplication {
  pname = "gmaps-cli";
  version = "0.1.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  dependencies = [ ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/gmaps-cli
  '';

  meta = {
    description = "CLI tool to search for places using Google Maps API";
    mainProgram = "gmaps-cli";
    license = lib.licenses.mit;
    maintainers = [ ];
  };
}
