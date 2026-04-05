---
name: browser-cli
description: Control Firefox browser from the command line. Use for web automation, scraping, testing, or any browser interaction tasks.
---

# Usage

```bash
browser-cli --list                       # List managed tabs
browser-cli --go "https://example.com"   # Open page, prints tab ID (e.g. abc123)
browser-cli abc123 <<< 'snap()'          # Execute JS in that tab
```

# JavaScript API

Actions return confirmations; use `snap()` to get page state. Refs `[N]` come
from `snap()` output. CSS selectors also work: `click("#submit")`,
`click("Sign In", "text")`.

```javascript
// Interaction
await click(1)                       // also: {double: true}
await type(2, "text")                // also: {clear: true}
await hover(3)
await drag(4, 5)
await select(6, "value")
key("Enter")

// Inspection
snap()                               // full snapshot first call,
                                     // diff vs previous on later calls
snap({full: true})                   // force full snapshot
snap({forms|links|buttons: true})    // filter by type (always full)
snap({text: "login"})                // filter by text (always full)
logs()                               // console logs

// Waiting
await wait(1000)                     // ms
await wait("idle")                   // DOM stable
await wait("text", "Success")        // text appears
await wait("gone", "Loading")        // text disappears

// Other
await download(url, "file.pdf")      // -> ~/Downloads/
await shot("/tmp/page.png")          // screenshot (omit path for data URL)
read()                               // article text via Readability
                                     // opts: {maxLength, includeMetadata}
```

Alternative to `read()`: `curl -sL "https://r.jina.ai/$URL"` returns clean
markdown without a browser tab — prefer for public static articles/docs.

# Snapshot Format

```
[1] heading "Welcome"
[2] input[email] "Email" [required]
[3] button "Sign In"
```

`[N]` = ref for click/type/etc. Shows role, name, and attrs like `[disabled]`,
`[checked]`, `[required]`.

# Example: Login Flow

```bash
browser-cli --go "https://example.com/login"   # -> tab h9Jk3b
browser-cli h9Jk3b <<< 'snap()'
# [1] input "Email"  [2] input "Password"  [3] button "Sign In"

browser-cli h9Jk3b <<'EOF'
await type(1, "user@test.com")
await type(2, "secret123")
await click(3)
await wait("text", "Welcome")
snap()
EOF
```

See [README.md](../../browser-cli/README.md) for installation and full API reference.
