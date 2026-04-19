---
name: screenshot-cli
description: Take screenshots non-interactively. Use to see the screen, debug UI, or capture a specific region by coordinates.
---

Prints output path on stdout. Default: `~/.claude/outputs/screenshot-TIMESTAMP.png`. View with the `read` tool.

```bash
screenshot-cli                      # Full screen (default)
screenshot-cli -w                   # Focused window (Linux only)
screenshot-cli -g "100,50 800x600"  # Region by logical coords 'X,Y WxH'
screenshot-cli -d 3                 # Delay 3s before capture
screenshot-cli /tmp/shot.png        # Custom output path
```

`-g` coords are **logical** (pre-scale): on a 1.5× display, `0,0 100x100` yields a 150×150 PNG. If reading pixel offsets from a previous screenshot, divide by your scale factor.
