# Shared option module imported by every per-skill homeModule (and the legacy
# `programs.mics-skills` module). Lets the user pick which agent harnesses get
# the skill definitions symlinked, instead of hard-coding ~/.claude + ~/.opencode
# in every skill.
{ lib, ... }:
{
  key = "mics-skills/common";

  options.programs.mics-skills = {
    skillDirs = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        ".claude/skills"
        ".opencode/skills"
      ];
      example = [ ".claude/skills" ];
      description = ''
        Directories (relative to `$HOME`) into which each enabled skill's
        definition is symlinked as `<dir>/<skill>/`. One entry per agent
        harness that should discover the skills.
      '';
    };
  };
}
