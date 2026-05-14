---
name: kagi
description: Search the web or summarize a URL via Kagi (no API credits used; session-token auth).
---

# Usage

The `kagi` CLI has two verbs: `search` (discover) and `summarize` (enrich a
known URL). The original `kagi-search` and the new `kagi-summarize` binary
names work as aliases.

## Search

Use for discovery: queries the web and returns Kagi's Quick Answer summary
plus optional result links.

```bash
# Quick Answer only (default)
kagi search "what is the capital of France"

# Include result links (default: 3)
kagi search -l "search query"

# More links
kagi search -l -n 10 "search query"

# JSON output for parsing
kagi search -j "search query" | jq '.results[0].url'

# Original kagi-search invocation still works:
kagi-search "search query"
```

## Summarize

Use when you already have a URL and want a structured summary — works well
as a fetch replacement for pages where you don't need the HTML, just the
gist.

```bash
# Markdown summary (default)
kagi summarize https://example.com/article

# Bullet-list takeaways
kagi summarize --takeaway https://example.com/article

# Plain text (strips markdown + HTML)
kagi summarize --text https://example.com/article

# Raw JSON
kagi summarize --json https://example.com/article

# Target language
kagi summarize --language ES https://example.com/article

# Alias form:
kagi-summarize https://example.com/article
```
