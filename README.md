# mics-skills

A collection of CLI tools and skills designed to be useful for LLM agents.

## Tools

| Tool                                    | Description                                                     | Skill                                        |
| --------------------------------------- | --------------------------------------------------------------- | -------------------------------------------- |
| [browser-cli](browser-cli/)             | Control Firefox browser from the command line                   | [SKILL.md](browser-cli/skill/SKILL.md)       |
| [buildbot-pr-check](buildbot-pr-check/) | Inspect Buildbot (buildbot-nix) CI for a PR                     | [SKILL.md](buildbot-pr-check/skill/SKILL.md) |
| [calendar-cli](calendar-cli/)           | Manage calendar events and send meeting invitations             | [SKILL.md](calendar-cli/skill/SKILL.md)      |
| [context7-cli](context7-cli/)           | Fetch up-to-date library documentation from Context7            | [SKILL.md](context7-cli/skill/SKILL.md)      |
| [db-cli](db-cli/)                       | Search Deutsche Bahn train connections                          | [SKILL.md](db-cli/skill/SKILL.md)            |
| [gmaps-cli](gmaps-cli/)                 | Search for places and get directions using Google Maps          | [SKILL.md](gmaps-cli/skill/SKILL.md)         |
| [kagi-search](kagi-search/)             | Search the web using Kagi with Quick Answer AI summaries        | [SKILL.md](kagi-search/skill/SKILL.md)       |
| [n8n-cli](n8n-cli/)                     | Manage n8n workflows, credentials, executions, tags, and data   | [SKILL.md](n8n-cli/skill/SKILL.md)           |
| [pexpect-cli](pexpect-cli/)             | Persistent pexpect sessions for interactive terminal automation | [SKILL.md](pexpect-cli/skill/SKILL.md)       |
| [screenshot-cli](screenshot-cli/)       | Cross-platform screenshots for macOS and KDE Wayland            | [SKILL.md](screenshot-cli/skill/SKILL.md)    |
| [tasker-cli](tasker-cli/)               | Deploy and trigger Android Tasker tasks via WebUI and adb       | [SKILL.md](tasker-cli/skill/SKILL.md)        |
| [weather-cli](weather-cli/)             | Weather forecasts worldwide via Bright Sky API (DWD/MOSMIX)     | [SKILL.md](weather-cli/skill/SKILL.md)       |

Each tool ships its skill definition under `<tool>/skill/` (installed to
`$out/share/skills/<tool>/`). The home-manager modules symlink that into
`~/.claude/skills/` so Claude Code and pi discover them automatically.

## Installation

### Using Nix Flakes

```bash
nix run github:Mic92/mics-skills#browser-cli
nix run github:Mic92/mics-skills#calendar-cli
nix run github:Mic92/mics-skills#context7-cli
nix run github:Mic92/mics-skills#db-cli
nix run github:Mic92/mics-skills#gmaps-cli
nix run github:Mic92/mics-skills#kagi-search
nix run github:Mic92/mics-skills#n8n-cli
nix run github:Mic92/mics-skills#pexpect-cli
nix run github:Mic92/mics-skills#screenshot-cli
nix run github:Mic92/mics-skills#tasker-cli
nix run github:Mic92/mics-skills#weather-cli

# Add to your flake inputs
{
  inputs.mics-skills.url = "github:Mic92/mics-skills";
}
```

### Using home-manager

This flake provides a home-manager module that installs the CLI tools and
symlinks the corresponding skill definitions into `~/.claude/skills/`. Claude
Code and pi discover them automatically.

Add the flake input and import the module:

```nix
# flake.nix
{
  inputs.mics-skills.url = "github:Mic92/mics-skills";
}
```

```nix
# home-manager configuration
{ inputs, pkgs, ... }:
{
  imports = [ inputs.mics-skills.homeManagerModules.default ];

  programs.mics-skills = {
    enable = true;
    package = inputs.mics-skills.packages.${pkgs.stdenv.hostPlatform.system};
  };
}
```

By default all skills are installed. To pick only the ones you need, set the
`skills` option:

```nix
programs.mics-skills = {
  enable = true;
  package = inputs.mics-skills.packages.${pkgs.stdenv.hostPlatform.system};
  skills = [
    "kagi-search"
    "pexpect-cli"
    "screenshot-cli"
  ];
};
```

Only the selected CLI tools and their skill definitions will be installed.

By default skill definitions are symlinked into both `~/.claude/skills/` and
`~/.opencode/skills/`. Override `programs.mics-skills.skillDirs` to target a
different set of agent harnesses:

```nix
programs.mics-skills.skillDirs = [ ".claude/skills" ];
```

### Per-skill modules

Each skill is also available as an individual Home Manager module. Importing a
module installs its CLI tool and skill definition — no extra options needed:

```nix
# home-manager configuration
{ inputs, ... }:
{
  imports = [
    inputs.mics-skills.homeModules.kagi-search
    inputs.mics-skills.homeModules.pexpect-cli
    inputs.mics-skills.homeModules.screenshot-cli
  ];
}
```

> List available modules with
> `nix eval github:Mic92/mics-skills#homeModules --apply builtins.attrNames`.

### Without home-manager

Every package installs its skill definition to `$out/share/skills/<name>/`, so
you can wire it up yourself from plain NixOS.

Here an example to using `symlinkJoin`:

```nix
let
  skills = pkgs.symlinkJoin {
    name = "mics-skills";
    paths = [ sk.kagi-search sk.pexpect-cli sk.screenshot-cli ];
  };
in
# ${skills}/share/skills/ now contains kagi-search/, pexpect-cli/, screenshot-cli/
```

## Development

```bash
nix develop
nix fmt
nix flake check
```

## License

MIT
