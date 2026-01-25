# mics-skills

A collection of CLI tools and skills designed to be useful for LLM agents.

## Packages

| Package                       | Description                                                     |
| ----------------------------- | --------------------------------------------------------------- |
| [browser-cli](browser-cli/)   | Control Firefox browser from the command line                   |
| [context7-cli](context7-cli/) | Fetch up-to-date library documentation from Context7            |
| [db-cli](db-cli/)             | Search Deutsche Bahn train connections                          |
| [gmaps-cli](gmaps-cli/)       | Search for places and get directions using Google Maps          |
| [kagi-search](kagi-search/)   | Search the web using Kagi with Quick Answer AI summaries        |
| [pexpect-cli](pexpect-cli/)   | Persistent pexpect sessions for interactive terminal automation |

## Skills

The `skills/` directory contains Claude skill definitions for use with Claude
Code or similar LLM coding assistants. Each skill provides usage examples and
references the package README for setup instructions.

| Skill                                        | Description                                       |
| -------------------------------------------- | ------------------------------------------------- |
| [browser-cli](skills/browser-cli/SKILL.md)   | Web automation, scraping, testing                 |
| [context7-cli](skills/context7-cli/SKILL.md) | Library documentation and code examples           |
| [db-cli](skills/db-cli/SKILL.md)             | Train route and schedule search                   |
| [gmaps-cli](skills/gmaps-cli/SKILL.md)       | Place search and directions                       |
| [kagi-search](skills/kagi-search/SKILL.md)   | Web search with AI summaries                      |
| [pexpect-cli](skills/pexpect-cli/SKILL.md)   | SSH, database, and interactive program automation |

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

# Add to your flake inputs
{
  inputs.mics-skills.url = "github:Mic92/mics-skills";
}
```

## Development

```bash
nix develop
nix fmt
nix flake check
```

## License

MIT
