{
  lib,
  python3,
  vdirsyncer,
  msmtp ? null,
}:

python3.pkgs.buildPythonApplication {
  pname = "calendar-cli";
  version = "1.0.0";

  src = ./.;

  pyproject = true;

  build-system = with python3.pkgs; [
    hatchling
  ];

  dependencies = with python3.pkgs; [
    icalendar
    python-dateutil
  ];

  makeWrapperArgs =
    let
      bins = [ vdirsyncer ] ++ lib.optional (msmtp != null) msmtp;
    in
    [
      "--suffix PATH : ${lib.makeBinPath bins}"
    ];

  nativeCheckInputs = with python3.pkgs; [
    pytestCheckHook
  ];

  meta = {
    description = "CLI tool for managing local vdirsyncer calendars";
    homepage = "https://github.com/Mic92/mics-skills";
    license = lib.licenses.mit;
    mainProgram = "calendar-cli";
  };
}
