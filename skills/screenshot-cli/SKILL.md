---
name: screenshot-cli
description: "Capture full-screen, window, or region screenshots on macOS and KDE Wayland. Use when needing to see the screen, take a screen capture, snapshot the display, or debug UI and graphical issues."
---

# Usage

```bash
screenshot-cli                    # Fullscreen (default)
screenshot-cli -w                 # Focused window
screenshot-cli -r                 # Interactive region selection
screenshot-cli -d 3               # Delay 3s before capture
screenshot-cli /tmp/shot.png      # Custom output path
screenshot-cli -s 1               # Specific monitor (macOS only)
```

Prints the output file path on stdout. Default: `~/.claude/outputs/screenshot-TIMESTAMP.png`

View the result with the `read` tool:

```bash
path=$(screenshot-cli)
# read "$path"
```
