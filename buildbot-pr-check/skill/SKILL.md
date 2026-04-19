---
name: buildbot-pr-check
description: Inspect Buildbot (buildbot-nix) CI for a PR. Use to find/watch the build for a PR, list failed sub-builds with their attrs, and fetch failing log tails.
---

```bash
buildbot-pr-check <pr-url>                                # eval build + per-sub-build status table
buildbot-pr-check <pr-url> --watch --interval 60          # poll until complete; exit 0=success 1=failure
buildbot-pr-check <pr-url> --failures --log-tail 80       # failed sub-builds: attr, error prop, stdio log tail + log_url
```

`<pr-url>` is a GitHub `…/pull/N` or Gitea `…/pulls/N` URL (omit to auto-detect
the current branch's PR via `gh`). The buildbot instance is discovered from the
forge's commit statuses; no config. Add `--json` for structured output:

```bash
buildbot-pr-check <pr-url> --failures --json | jq -r '.failures[] | "\(.attr)\t\(.status)\t\(.log_url // "-")"'
```

Need more than the tail? `log_url` is a plain `…/api/v2/logs/<id>/raw_inline`
endpoint — `curl -s "$log_url" | tail -n 500` / `| grep error:`.

Result codes are reported by name: `SUCCESS WARNINGS FAILURE SKIPPED EXCEPTION RETRY CANCELLED` (`RUNNING` while incomplete).
