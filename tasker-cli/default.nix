{
  lib,
  buildPythonApplication,
  hatchling,
  android-tools,
  makeWrapper,
}:

buildPythonApplication {
  pname = "tasker-cli";
  version = "1.0.0";
  pyproject = true;

  src = ./.;

  build-system = [ hatchling ];

  nativeBuildInputs = [ makeWrapper ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r ${./skill} $out/share/skills/tasker-cli
    wrapProgram $out/bin/tasker-cli \
      --prefix PATH : ${lib.makeBinPath [ android-tools ]}
  '';

  meta = with lib; {
    description = "CLI tool to deploy and trigger Tasker tasks via WebUI API and adb";
    homepage = "https://github.com/Mic92/mics-skills";
    license = licenses.mit;
    maintainers = with maintainers; [ mic92 ];
    mainProgram = "tasker-cli";
  };
}
