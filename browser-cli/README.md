# Browser CLI

A command-line interface for controlling Firefox through WebExtensions API.
Optimized for LLM agents with limited context windows.

## Overview

Browser CLI consists of three components:

1. **Firefox Extension** - Executes commands in the browser and provides visual
   feedback
2. **Native Messaging Bridge** - Facilitates communication between the CLI and
   extension
3. **CLI Client** - Minimal command-line tool that executes JavaScript via stdin

## Installation

### For Nix Users

```bash
nix run github:Mic92/mics-skills#browser-cli -- --help
```

### Manual Installation

1. **Install the Firefox Extension**
   - Open Firefox
   - Navigate to `about:debugging`
   - Click "This Firefox"
   - Click "Load Temporary Add-on"
   - Select `manifest.json` from the `extension` directory

2. **Install Native Messaging Host**
   ```bash
   browser-cli --install-host
   ```

## Usage

See [skills/browser-cli/SKILL.md](../skills/browser-cli/SKILL.md) for usage
examples and JavaScript API reference.

## Architecture

```
┌─────────────┐     Unix Socket     ┌──────────────┐     Native      ┌────────────┐
│    CLI      │ ◄─────────────────► │    Bridge    │ ◄─────────────► │ Extension  │
│  (stdin)    │                     │   Server     │    Messaging    │            │
└─────────────┘                     └──────────────┘                 └────────────┘
```

## Development

### Project Structure

```
browser-cli/
├── extension/          # Firefox WebExtension
│   ├── manifest.json
│   ├── background.js   # Extension service worker
│   └── content.js      # Page automation and JS API
├── browser_cli/        # Python CLI package
│   ├── cli.py          # CLI entry point
│   ├── client.py       # Unix socket client
│   ├── bridge.py       # Native messaging bridge
│   └── server.py       # Bridge server
└── pyproject.toml
```

### Building

For Nix users:

```bash
nix build .#browser-cli
```

## Troubleshooting

### Extension Not Connecting

1. Ensure Firefox is running
2. The Browser CLI extension is installed
3. Native messaging host is installed: `browser-cli --install-host`
4. Check Firefox console for errors: `Ctrl+Shift+J`

### Commands Timing Out

- Use `wait()` for dynamic content: `await wait("text", "Loaded")`
- Check element refs are current: `snap()` to refresh

### Stale Refs

Refs are reset on each snapshot. If you get "Element [N] not found", call
`snap()` to get fresh refs.

## License

MIT
