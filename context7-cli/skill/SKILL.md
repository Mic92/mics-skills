---
name: context7-cli
description: Current API docs + code snippets for third-party libraries/frameworks. Use to verify exact signatures/usage.
---

Two-step: `search` resolves a library name to a Context7 ID, then `docs` fetches a few focused snippets for that ID. IDs are not guessable — always search first. Both args are required for both commands.

```bash
# 1. Find the library ID — output shows IDs, ⭐, snippet count, and available versions
context7-cli search nextjs "middleware"
#   /vercel/next.js   ⭐ 131k   Versions: v15.1.8, v13.5.11, ...

# 2. Fetch docs — query is semantic, be specific (output is ~5KB, don't waste it on broad topics)
context7-cli docs /vercel/next.js "middleware matcher config"

# Pin version (only ones listed in search output work)
context7-cli docs /vercel/next.js/v15.1.8 "app router migration"
```
