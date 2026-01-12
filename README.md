# mics-skills

A collection of CLI tools and skills designed to be useful for LLM agents.

## Packages

### browser-cli

Control Firefox browser from the command line. Useful for web automation, scraping, and testing.

```bash
nix run github:Mic92/mics-skills#browser-cli
```

### db-cli

CLI tool for searching Deutsche Bahn train connections.

```bash
nix run github:Mic92/mics-skills#db-cli
```

### gmaps-cli

CLI tool to search for places using Google Maps API.

```bash
nix run github:Mic92/mics-skills#gmaps-cli
```

### pexpect-cli

Persistent pexpect sessions for automating interactive terminal applications.

```bash
nix run github:Mic92/mics-skills#pexpect-cli
```

## Skills

The `skills/` directory contains Claude skill definitions that can be used with
Claude Code or similar LLM coding assistants:

- `skills/browser-cli/SKILL.md` - Instructions for using browser-cli
- `skills/pexpect-cli/SKILL.md` - Instructions for using pexpect-cli

## Installation

### Using Nix Flakes

```bash
# Run a tool directly
nix run github:Mic92/mics-skills#browser-cli

# Add to your flake inputs
{
  inputs.mics-skills.url = "github:Mic92/mics-skills";
}
```

### Development

```bash
nix develop
nix flake check
```

## License

MIT
