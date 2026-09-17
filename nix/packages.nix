{
  callPackage,
  callPackages,
  python3,
  vdirsyncer,
  msmtp,
  android-tools,
  makeWrapper,
}:
let
  pyCall = python3.pkgs.callPackage;
in
{
  browser-cli = pyCall ../browser-cli { };
  browser-cli-extension = (callPackages ../firefox-extensions { }).browser-cli-extension;
  calendar-cli = callPackage ../calendar-cli { inherit python3 vdirsyncer msmtp; };
  context7-cli = pyCall ../context7-cli { };
  db-cli = callPackage ../db-cli { };
  gmaps-cli = pyCall ../gmaps-cli { };
  kagi-search = pyCall ../kagi-search { };
  pexpect-cli = callPackage ../pexpect-cli { };
  # agent-friendly frontend for pueue
  queue = callPackage ../queue { };
  screenshot-cli = pyCall ../screenshot-cli { };
  tasker-cli = pyCall ../tasker-cli { inherit android-tools makeWrapper; };
  weather-cli = pyCall ../weather-cli { };
}
