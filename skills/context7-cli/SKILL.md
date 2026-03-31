---
name: context7-cli
description: Fetch up-to-date library documentation and code examples from Context7. Use for getting current API docs and snippets for any library or framework.
---

Two-step: `search` resolves a library name to a Context7 ID, then `docs` fetches focused documentation for that ID. IDs are not guessable — always search first.

```bash
# 1. Find the library ID (output shows IDs like /reactjs/react.dev)
context7-cli search react "hooks"

# 2. Fetch docs using the ID + a topic query
context7-cli docs /reactjs/react.dev "useState examples"

# Pin to a specific version
context7-cli docs /vercel/next.js/v14.3.0 "app router"
```
