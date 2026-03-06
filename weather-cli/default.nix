{
  lib,
  buildPythonApplication,
  hatchling,
}:

buildPythonApplication {
  pname = "weather-cli";
  version = "1.0.0";
  pyproject = true;

  src = ./.;

  build-system = [ hatchling ];

  meta = with lib; {
    description = "CLI tool for weather forecasts using Bright Sky API (DWD/MOSMIX, worldwide)";
    homepage = "https://github.com/Mic92/mics-skills";
    license = licenses.mit;
    maintainers = with maintainers; [ mic92 ];
    mainProgram = "weather-cli";
  };
}
