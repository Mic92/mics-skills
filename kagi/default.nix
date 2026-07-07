{
  lib,
  buildPythonApplication,
  hatchling,
  beautifulsoup4,
  pytestCheckHook,
}:

buildPythonApplication {
  pname = "kagi";
  version = "0.3.0";

  src = ./.;

  pyproject = true;

  build-system = [ hatchling ];

  dependencies = [ beautifulsoup4 ];

  nativeCheckInputs = [ pytestCheckHook ];

  pythonImportsCheck = [ "kagi" ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/kagi
    # Backward-compat: pre-verbs skill name. Symlink, not a copy.
    ln -s kagi $out/share/skills/kagi-search
  '';

  meta = {
    description = "CLI tool for Kagi (search + summarize) using session tokens";
    mainProgram = "kagi";
    license = lib.licenses.mit;
    maintainers = [ ];
  };
}
