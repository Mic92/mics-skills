{
  lib,
  config,
  ...
}:
let
  cfg = config.programs.mics-skills;

  registry = import ./skills.nix;

  # The legacy option module only exposes the "canonical" skills: entries that
  # map 1:1 onto a package of the same name (i.e. no packaging variants like
  # `browser-cli-with-extension`).
  allSkills = builtins.filter (name: (registry.${name}.package or name) == name) (
    builtins.attrNames registry
  );
in
{
  imports = [ ./home-manager-common.nix ];

  options.programs.mics-skills = {
    enable = lib.mkEnableOption "mics-skills LLM agent tools";

    skills = lib.mkOption {
      type = lib.types.listOf (lib.types.enum allSkills);
      default = allSkills;
      description = ''
        Which skills to install. Each entry installs the CLI tool into
        `home.packages` and the corresponding skill definition into every
        directory listed in `programs.mics-skills.skillDirs`.

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
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = ''
        Deprecated. Skill definitions now ship inside the packages at
        `$out/share/skills/<name>/`; this option is ignored.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    warnings =
      lib.optional (cfg.skillsSrc != null)
        "programs.mics-skills.skillsSrc is deprecated and ignored; skill files now ship inside the packages.";

    home.packages = map (name: cfg.package.${name}) cfg.skills;

    # Symlink the skill directory shipped inside each package into every
    # configured agent skills directory.
    home.file = lib.listToAttrs (
      lib.concatMap (
        name:
        map (dir: {
          name = "${dir}/${name}";
          value.source = "${cfg.package.${name}}/share/skills/${name}";
        }) cfg.skillDirs
      ) cfg.skills
    );
  };
}
