# screenshot-cli

Cross-platform screenshot CLI tool for macOS and KDE Wayland (Linux).

## Backends

| Platform    | Backend       | Notes                        |
| ----------- | ------------- | ---------------------------- |
| macOS       | screencapture | Built-in, no setup required  |
| KDE Wayland | spectacle     | KDE's native screenshot tool |
| Wayland     | grim          | Fallback for non-KDE Wayland |

## Installation

### Using Nix Flakes

```bash
nix run github:Mic92/mics-skills#screenshot-cli
```

### Manual

Ensure one of the backends is installed and available in `$PATH`:

- **macOS**: `screencapture` (ships with macOS)
- **KDE**: `spectacle`
- **Wayland**: `grim` (+ `slurp` for region selection)

## Usage

```bash
# Fullscreen screenshot (default)
screenshot-cli

# Capture focused window
screenshot-cli -w

# Interactive region selection
screenshot-cli -r

# Delay 3 seconds, then capture
screenshot-cli -d 3

# Save to specific file
screenshot-cli /tmp/my-screenshot.png

# Capture specific screen (macOS only)
screenshot-cli -s 1

# Force a specific backend
SCREENSHOT_BACKEND=grim screenshot-cli
```

## Output

Prints the path to the saved screenshot file on stdout. Default output
directory is `~/.claude/outputs/`.

## Options

| Option               | Description                                 |
| -------------------- | ------------------------------------------- |
| `-f`, `--fullscreen` | Capture entire screen (default)             |
| `-w`, `--window`     | Capture the focused window                  |
| `-r`, `--region`     | Interactive region selection                |
| `-d`, `--delay`      | Delay before capture (seconds)              |
| `-s`, `--screen`     | Screen number, 0-indexed (macOS fullscreen) |
| `-h`, `--help`       | Show help                                   |

## License

MIT
