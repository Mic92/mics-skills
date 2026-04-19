{ self, ... }:
let
  mkSkillModule =
    name:
    {
      packages ? null,
      extra ? { },
      ...
    }:
    { pkgs, ... }:
    let
      system = pkgs.stdenv.hostPlatform.system;
      packageNames = if packages != null then packages else [ name ];
    in
    {
      home.packages = map (p: self.packages.${system}.${p}) packageNames;
      home.file.".claude/skills/${name}".source = "${self}/skills/${name}";
      home.file.".opencode/skills/${name}".source = "${self}/skills/${name}";
      imports = [ extra ];
    };

in
{

  flake.homeModules = builtins.mapAttrs mkSkillModule {
    "browser-cli" = { };
    "browser-cli-with-extension" = {
      packages = [ "browser-cli" ];
      extra =
        { system, ... }:
        {
          programs.firefox.profiles.default.extensions.packages =
            self.packages.${system}.browser-cli-extension;
        };
    };
    "buildbot-pr-check" = { };
    "calendar-cli" = { };
    "context7-cli" = { };
    "db-cli" = { };
    "gmaps-cli" = { };
    "kagi-search" = { };
    "n8n-cli" = { };
    "pexpect-cli" = { };
    "screenshot-cli" = { };
    "tasker-cli" = { };
    "weather-cli" = { };
  };
}
