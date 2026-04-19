{
  lib,
  buildPythonApplication,
  hatchling,
  beautifulsoup4,
}:

buildPythonApplication {
  pname = "kagi-search";
  version = "0.1.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  dependencies = [ beautifulsoup4 ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/kagi-search
  '';

  meta = {
    description = "CLI tool for searching Kagi using session tokens";
    mainProgram = "kagi-search";
    license = lib.licenses.mit;
    maintainers = [ ];
  };
}
