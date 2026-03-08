# mics-skills

A collection of CLI tools and skills designed to be useful for LLM agents.

## Packages

| Package                           | Description                                                     |
| --------------------------------- | --------------------------------------------------------------- |
| [browser-cli](browser-cli/)       | Control Firefox browser from the command line                   |
| [context7-cli](context7-cli/)     | Fetch up-to-date library documentation from Context7            |
| [db-cli](db-cli/)                 | Search Deutsche Bahn train connections                          |
| [gmaps-cli](gmaps-cli/)           | Search for places and get directions using Google Maps          |
| [kagi-search](kagi-search/)       | Search the web using Kagi with Quick Answer AI summaries        |
| [pexpect-cli](pexpect-cli/)       | Persistent pexpect sessions for interactive terminal automation |
| [screenshot-cli](screenshot-cli/) | Cross-platform screenshots for macOS and KDE Wayland            |
| [tasker-cli](tasker-cli/)         | Deploy and trigger Android Tasker tasks via WebUI and adb       |
| [weather-cli](weather-cli/)       | Weather forecasts worldwide via Bright Sky API (DWD/MOSMIX)     |

## Skills

The `skills/` directory contains Claude skill definitions for use with Claude
Code or similar LLM coding assistants. Each skill provides usage examples and
references the package README for setup instructions.

| Skill                                            | Description                                       |
| ------------------------------------------------ | ------------------------------------------------- |
| [browser-cli](skills/browser-cli/SKILL.md)       | Web automation, scraping, testing                 |
| [context7-cli](skills/context7-cli/SKILL.md)     | Library documentation and code examples           |
| [db-cli](skills/db-cli/SKILL.md)                 | Train route and schedule search                   |
| [gmaps-cli](skills/gmaps-cli/SKILL.md)           | Place search and directions                       |
| [kagi-search](skills/kagi-search/SKILL.md)       | Web search with AI summaries                      |
| [pexpect-cli](skills/pexpect-cli/SKILL.md)       | SSH, database, and interactive program automation |
| [screenshot-cli](skills/screenshot-cli/SKILL.md) | Screenshot capture (macOS + KDE Wayland)          |
| [tasker-cli](skills/tasker-cli/SKILL.md)         | Deploy and trigger Android Tasker tasks            |
| [weather-cli](skills/weather-cli/SKILL.md)       | Weather forecasts worldwide (DWD/MOSMIX)          |

## Installation

### Using Nix Flakes

```bash
# Run a tool directly
nix run github:Mic92/mics-skills#browser-cli
nix run github:Mic92/mics-skills#context7-cli
nix run github:Mic92/mics-skills#db-cli
nix run github:Mic92/mics-skills#gmaps-cli
nix run github:Mic92/mics-skills#kagi-search
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
    skillsSrc = inputs.mics-skills;
  };
}
```

By default all skills are installed. To pick only the ones you need, set the
`skills` option:

```nix
programs.mics-skills = {
  enable = true;
  package = inputs.mics-skills.packages.${pkgs.stdenv.hostPlatform.system};
  skillsSrc = inputs.mics-skills;
  skills = [
    "kagi-search"
    "pexpect-cli"
    "screenshot-cli"
  ];
};
```

Only the selected CLI tools and their skill definitions will be installed.

## Development

```bash
nix develop
nix fmt
nix flake check
```

## License

MIT
