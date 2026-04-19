{
  lib,
  buildPythonApplication,
  hatchling,
  pytestCheckHook,
}:

buildPythonApplication {
  pname = "n8n-cli";
  version = "0.1.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  dependencies = [ ];

  nativeCheckInputs = [ pytestCheckHook ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/n8n-cli
  '';

  meta = {
    description = "Python CLI for n8n API: credentials, workflow JSON, execution data";
    mainProgram = "n8n-cli";
    license = lib.licenses.mit;
    maintainers = [ ];
  };
}
