{
  lib,
  config,
  ...
}:
let
  cfg = config.programs.mics-skills;

  # Each skill maps to a package name and a skills/ subdirectory.
  allSkills = [
    "browser-cli"
    "calendar-cli"
    "context7-cli"
    "db-cli"
    "gmaps-cli"
    "kagi-search"
    "n8n-cli"
    "pexpect-cli"
    "screenshot-cli"
    "tasker-cli"
    "weather-cli"
  ];
in
{
  options.programs.mics-skills = {
    enable = lib.mkEnableOption "mics-skills LLM agent tools";

    skills = lib.mkOption {
      type = lib.types.listOf (lib.types.enum allSkills);
      default = allSkills;
      description = ''
        Which skills to install. Each entry installs the CLI tool into
        `home.packages` and the corresponding skill definition into
        `~/.claude/skills/<name>/`.

        Defaults to all available skills.
      '';
      example = [
        "kagi-search"
        "screenshot-cli"
        "pexpect-cli"
      ];
    };

    package = lib.mkOption {
      type = lib.types.attrsOf lib.types.package;
      description = ''
        Attribute set of mics-skills packages (e.g.
        `inputs.mics-skills.packages.''${system}`).
      '';
    };

    skillsSrc = lib.mkOption {
      type = lib.types.path;
      description = ''
        Path to the mics-skills source tree. Used to locate the `skills/`
        directory. Typically `inputs.mics-skills` (the flake source).
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = map (name: cfg.package.${name}) cfg.skills;

    # Symlink only the selected skill directories.
    home.file = lib.listToAttrs (
      map (name: {
        name = ".claude/skills/${name}";
        value.source = "${cfg.skillsSrc}/skills/${name}";
      }) cfg.skills
    );
  };
}
