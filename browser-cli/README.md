# Browser CLI

A command-line interface for controlling Firefox/LibreWolf through WebExtensions
API. Optimized for LLM agents with limited context windows. Works with a GUI
browser or headlessly via [browsh](https://www.brow.sh/).

## Overview

Browser CLI consists of three components:

1. **Firefox Extension** - Executes commands in the browser and provides visual
   feedback
2. **Native Messaging Bridge** - Facilitates communication between the CLI and
   extension
3. **CLI Client** - Minimal command-line tool that executes JavaScript via stdin

When no GUI browser is running, browser-cli automatically starts
[browsh](https://www.brow.sh/) as a headless backend. Browsh runs a headless
Firefox/LibreWolf instance that loads the browser-cli extension, providing the
full API without needing a display.

## Installation

### For Nix Users

```bash
nix run github:Mic92/mics-skills#browser-cli -- --help
```

### Manual Installation

1. **Install the Firefox Extension**
   - Open Firefox/LibreWolf
   - Navigate to `about:debugging`
   - Click "This Firefox"
   - Click "Load Temporary Add-on"
   - Select `manifest.json` from the `extension` directory

2. **Install Native Messaging Host**
   ```bash
   browser-cli --install-host
   ```

3. **(Optional) Install browsh for headless mode**
   - See [browsh installation](https://www.brow.sh/docs/installation/)
   - Install the browser-cli extension into browsh's Firefox profile
     (see [Headless Mode](#headless-mode) below)

## Usage

See [skills/browser-cli/SKILL.md](../skills/browser-cli/SKILL.md) for usage
examples and JavaScript API reference.

## Headless Mode

When browser-cli can't connect to a running browser, it automatically starts
[browsh](https://www.brow.sh/) as a headless backend. Browsh launches a
headless Firefox/LibreWolf instance with the browser-cli extension loaded from
its profile, giving full API access without a GUI.

### Configuring the Browser Path

If you use LibreWolf or a non-standard Firefox path, configure it via one of
(in priority order):

1. **CLI argument**: `--firefox-path /path/to/firefox`
2. **Environment variable**: `BROWSER_CLI_FIREFOX_PATH=/path/to/firefox`
3. **Config file**: `~/.config/browser-cli/config.toml`

   ```toml
   firefox_path = "/Applications/Nix Casks/LibreWolf.app/Contents/MacOS/librewolf"
   ```

The config file follows XDG conventions (`$XDG_CONFIG_HOME/browser-cli/config.toml`).

### Installing the Extension in Browsh

Browsh maintains its own Firefox profile. To use browser-cli headlessly, the
extension must be installed there:

1. Start browsh with its GUI to access the profile:
   ```bash
   browsh --firefox.with-gui --firefox.path /path/to/firefox
   ```
2. Install the browser-cli extension from `about:debugging` as above
3. Install the native messaging host: `browser-cli --install-host`

Once installed, the extension persists in browsh's profile and will load
automatically on subsequent headless runs.

### How It Works

```
browser-cli <<< 'snap()'
  → tries Unix socket → no browser running
  → spawns browsh via pty.fork()
  → browsh starts headless Firefox/LibreWolf
  → Firefox loads browser-cli extension from browsh's profile
  → extension starts native messaging bridge → socket appears
  → browser-cli retries → connects → full API available
```

Browsh requires a TTY, so browser-cli allocates a PTY via `pty.fork()` and
drains its output in a background thread. The browsh process ignores SIGHUP
so it survives after browser-cli exits, and subsequent browser-cli invocations
reuse the running instance.

## Architecture

```
┌─────────────┐     Unix Socket     ┌──────────────┐     Native      ┌────────────┐
│    CLI      │ ◄─────────────────► │    Bridge    │ ◄─────────────► │ Extension  │
│  (stdin)    │                     │   Server     │    Messaging    │            │
└─────────────┘                     └──────────────┘                 └────────────┘
                                                                          │
                                                              ┌───────────┴───────────┐
                                                              │  Firefox / LibreWolf  │
                                                              │  (GUI or headless     │
                                                              │   via browsh)         │
                                                              └───────────────────────┘
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
│   ├── client.py       # Unix socket client (auto-starts browsh)
│   ├── bridge.py       # Native messaging bridge
│   ├── server.py       # Bridge server
│   ├── browsh.py       # Browsh headless backend management
│   └── config.py       # Config file handling
└── pyproject.toml
```

### Building

For Nix users:

```bash
nix build .#browser-cli
```

## Troubleshooting

### Extension Not Connecting

1. Ensure Firefox/LibreWolf is running, or browsh is installed for headless mode
2. The Browser CLI extension is installed (in the browser or browsh's profile)
3. Native messaging host is installed: `browser-cli --install-host`
4. Check Firefox console for errors: `Ctrl+Shift+J`

### Headless Mode Not Starting

1. Ensure `browsh` is in PATH
2. Configure the Firefox/LibreWolf path (see [Configuring the Browser Path](#configuring-the-browser-path))
3. Verify the extension is installed in browsh's profile:
   ```bash
   ls ~/Library/Application\ Support/browsh/firefox_profile/extensions/
   # Should contain: browser-cli-controller@thalheim.io.xpi
   ```
4. Run with `--debug` for detailed logs: `browser-cli --debug <<< 'snap()'`

### Commands Timing Out

- Use `wait()` for dynamic content: `await wait("text", "Loaded")`
- Check element refs are current: `snap()` to refresh

### Stale Refs

Refs are reset on each snapshot. If you get "Element [N] not found", call
`snap()` to get fresh refs.

## Known Issues

### Extra `example.com` tab when no managed tabs exist

When no managed tabs exist and the first command uses `tab("url")`, the bridge
auto-creates a throwaway `example.com` tab to bootstrap content script
execution. Firefox blocks content script injection on `about:blank` and `data:`
URIs, so a real HTTP page is required. The `tab()` call then creates the
intended tab and subsequent API calls (`snap()`, `click()`, etc.) are correctly
proxied to it. The leftover `example.com` tab can be ignored or closed manually.

## License

MIT
