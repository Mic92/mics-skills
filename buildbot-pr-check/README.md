# buildbot-pr-check

Inspect Buildbot (buildbot-nix) CI for a GitHub/Gitea pull request: find/watch
the eval build (even while it is still running), list failed sub-builds with
their flake `attr`, and fetch failing log tails — without hand-crafting
`/api/v2/...` curl pipelines.

## Usage

```bash
buildbot-pr-check https://github.com/OWNER/REPO/pull/123
buildbot-pr-check https://github.com/OWNER/REPO/pull/123 --watch --interval 30
buildbot-pr-check https://github.com/OWNER/REPO/pull/123 --failures --log-tail 120
```

Add `--json` for a single machine-readable document. Each failure carries a
`log_url` (`…/api/v2/logs/<id>/raw_inline`) for `curl | tail/grep` when the
bundled tail is not enough.

## Build discovery

The buildbot instance is discovered from the forge: buildbot-nix posts a
commit status / check-run with `target_url` pointing at the eval build as soon
as it starts. The tool reads that, then talks to buildbot directly. No
configuration needed.

## Exit codes

`0` on success, `1` on failure/exception/cancelled.
