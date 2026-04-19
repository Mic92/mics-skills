{
  lib,
  buildPythonApplication,
  hatchling,
  pytestCheckHook,
}:

buildPythonApplication {
  pname = "buildbot-pr-check";
  version = "0.2.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  # Runtime: stdlib only.
  dependencies = [ ];

  nativeCheckInputs = [ pytestCheckHook ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/buildbot-pr-check
  '';

  pythonImportsCheck = [ "buildbot_pr_check" ];

  meta = {
    description = "Inspect Buildbot (buildbot-nix) CI for a PR";
    mainProgram = "buildbot-pr-check";
    license = lib.licenses.mit;
    maintainers = [ ];
  };
}
