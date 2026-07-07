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
  buildbot-pr-check = pyCall ../buildbot-pr-check { };
  browser-cli-extension = (callPackages ../firefox-extensions { }).browser-cli-extension;
  calendar-cli = callPackage ../calendar-cli { inherit python3 vdirsyncer msmtp; };
  context7-cli = pyCall ../context7-cli { };
  db-cli = callPackage ../db-cli { };
  gmaps-cli = pyCall ../gmaps-cli { };
  kagi-search = pyCall ../kagi-search { };
  n8n-cli = pyCall ../n8n-cli { };
  pexpect-cli = callPackage ../pexpect-cli { };
  screenshot-cli = pyCall ../screenshot-cli { };
  tasker-cli = pyCall ../tasker-cli { inherit android-tools makeWrapper; };
  weather-cli = pyCall ../weather-cli { };
}
