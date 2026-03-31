---
name: context7-cli
description: "Fetch up-to-date library documentation, usage examples, function signatures, and version-specific API references from Context7. Use when needing docs for a library, SDK reference, package documentation, or latest API details."
---

# Usage

Workflow: search to find library ID, then fetch docs with that ID.

```bash
# 1. Search for libraries by name
context7-cli search react "how to use hooks"

# 2. Get documentation using library ID from search
context7-cli docs /vercel/next.js "middleware authentication"

# With specific version
context7-cli docs /vercel/next.js/v14.3.0 "app router"

# JSON output for programmatic use
context7-cli search --json react "hooks" | jq '.results[0].id'
context7-cli docs --json /vercel/next.js "routing"

# With explicit API key
context7-cli -k "ctx7sk_xxx" search react "hooks"
```
