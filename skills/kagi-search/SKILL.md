---
name: kagi-search
description: Search the web using Kagi. Use for web searches with Quick Answer AI summaries.
---

# Usage

```bash
# Basic search (includes Quick Answer)
kagi-search "what is the capital of France"

# JSON output for parsing
kagi-search -j "search query" | jq '.results[0].url'

# Extract Quick Answer
kagi-search -j "search query" | jq '.quick_answer.markdown'

# Limit number of results
kagi-search -n 5 "search query"

# With explicit token
kagi-search -t "TOKEN" "search query"

# Enable debug logging
kagi-search -d "search query"
```

# Output Format

Results include:

- Quick Answer (AI-generated summary with references)
- Search results with title, URL, and snippet

See [README.md](../../kagi-search/README.md) for setup and configuration.
