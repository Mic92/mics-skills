{
  stdenv,
  callPackage,
  callPackages,
  python3,
  vdirsyncer,
  msmtp,
  android-tools,
  makeWrapper,
  kdePackages,
  # screenshot-cli backends, hoisted here so downstream users can drop one via
  # `.override`, e.g. `.override { spectacle = null; }` on non-KDE systems.
  spectacle ? if stdenv.hostPlatform.isLinux then kdePackages.spectacle else null,
}:
let
  pyCall = python3.pkgs.callPackage;
  kagi = pyCall ../kagi { };
in
{
  browser-cli = pyCall ../browser-cli { };
  buildbot-pr-check = pyCall ../buildbot-pr-check { };
  browser-cli-extension = (callPackages ../firefox-extensions { }).browser-cli-extension;
  calendar-cli = callPackage ../calendar-cli { inherit python3 vdirsyncer msmtp; };
  context7-cli = pyCall ../context7-cli { };
  db-cli = callPackage ../db-cli { };
  gmaps-cli = pyCall ../gmaps-cli { };
  inherit kagi;
  # Backward-compat alias for the pre-verbs `kagi-search` package name.
  kagi-search = kagi;
  n8n-cli = pyCall ../n8n-cli { };
  pexpect-cli = callPackage ../pexpect-cli { };
  screenshot-cli = pyCall ../screenshot-cli {
    inherit spectacle;
  };
  tasker-cli = pyCall ../tasker-cli { inherit android-tools makeWrapper; };
  weather-cli = pyCall ../weather-cli { };
}
