---
name: context7-cli
description: Fetch up-to-date library documentation and code examples from Context7. Use for getting current API docs and snippets for any library or framework.
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
