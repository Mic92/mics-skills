---
name: kagi
description: Search the web or summarize a URL via Kagi (no API credits used; session-token auth).
---

# Usage

The `kagi` CLI has two verbs: `search` (discover) and `summarize` (enrich a
known URL). `kagi-search` and `kagi-summarize` are also available as
standalone binaries (shortcuts for the corresponding verbs).

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

# Plain text (strip markdown markup)
kagi search --text "search query"

# JSON for scripts (note: .results is empty unless you pass -l)
kagi search -j -l "search query" | jq -r '.quick_answer.references[].url'

# Shortcut form:
kagi-search "search query"
```

**Reading vs scripting.** The default (no `-j`) output _is_ a synthesized,
cited answer — Kagi's Quick Answer plus a References list of source URLs. Use
bare `kagi search` whenever you're _reading_ the result: it's already clean
markdown and uses fewer tokens than JSON. Don't reach for `-j` just because
you're an agent — JSON only pays off when a _script_ parses fields. For that
case use `-j` (add `-l -n 10` to populate `.results` with raw candidate
links); the JSON shape is `{results, quick_answer: {markdown, references:
[{title, url, contribution}]}}`.

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
kagi summarize -j https://example.com/article

# Target language
kagi summarize --language ES https://example.com/article

# Alias form:
kagi-summarize https://example.com/article
```

Both verbs share the same output flags: `-j`/`--json`, `--text`, `--markdown`
(default).
