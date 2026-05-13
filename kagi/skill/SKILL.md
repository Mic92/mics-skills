---
name: kagi
description: Search the web and summarize URLs via Kagi. Use for web searches with Quick Answer AI summaries.
---

# Usage

The `kagi` CLI exposes one verb today (`search`); a `summarize` verb is
coming. The backward-compat `kagi-search` alias continues to work.

## Search

```bash
# Quick Answer only (default)
kagi search "what is the capital of France"

# Include search result links (default: 3)
kagi search -l "search query"

# More links
kagi search -l -n 10 "search query"

# JSON output for parsing
kagi search -j "search query" | jq '.results[0].url'

# Original kagi-search invocation still works:
kagi-search "search query"
```
