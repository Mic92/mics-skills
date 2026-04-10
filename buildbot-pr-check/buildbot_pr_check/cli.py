"""CLI for inspecting Buildbot (buildbot-nix) CI for a pull request.

Resolves a PR to its eval build and sub-builds::

    --watch          poll until complete
    --failures       only failed sub-builds, with log tail + raw log_url

Deeper log inspection is intentionally out of scope: every failure carries a
``log_url`` pointing at ``/api/v2/logs/<id>/raw_inline``; pipe that through
``curl | tail/grep`` if the bundled tail is not enough.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

from . import gitea_api, github_api
from .buildbot_api import Build, BuildbotClient, EvalBuild
from .exceptions import BuildbotCheckError
from .git import get_current_branch_pr_url
from .reporting import print_eval_build, print_failures
from .url_parser import PRInfo, get_pr_info, parse_buildbot_url


# --------------------------------------------------------------------------- #
# PR → eval build discovery
# --------------------------------------------------------------------------- #


def _resolve_pr(arg: str | None) -> PRInfo:
    if arg and arg.isdigit():
        # bare PR number → use current repo via gh
        url = get_current_branch_pr_url()
        if not url:
            msg = "Bare PR number given but could not detect repo via `gh`"
            raise BuildbotCheckError(msg)
        info = get_pr_info(url)
        return PRInfo(info.platform, info.host, info.owner, info.repo, arg)
    if arg:
        return get_pr_info(arg)
    url = get_current_branch_pr_url()
    if not url:
        msg = (
            "No PR URL given and could not auto-detect one for the current branch. "
            "Pass a GitHub/Gitea PR URL."
        )
        raise BuildbotCheckError(msg)
    return get_pr_info(url)


def _head_sha(pr: PRInfo) -> str:
    if pr.platform == "github":
        return github_api.get_pr_head_sha(pr.owner, pr.repo, pr.pr_num)
    return gitea_api.get_pr_head_sha(pr.host, pr.owner, pr.repo, pr.pr_num)


def _discover_eval_build(pr: PRInfo, head_sha: str) -> tuple[BuildbotClient, Build]:
    """Find the top-level nix-eval build via the forge's commit-status target URLs.

    buildbot-nix posts a pending status as soon as the eval build starts, so
    this also locates in-progress builds.
    """
    if pr.platform == "github":
        urls = github_api.get_buildbot_urls_from_github(pr.owner, pr.repo, head_sha)
    else:
        urls = gitea_api.get_buildbot_urls_from_gitea(pr.host, pr.owner, pr.repo, head_sha)

    for url in urls:
        ref = parse_buildbot_url(url)
        if ref.builder_id is None or ref.build_num is None:
            continue
        client = BuildbotClient(ref.base_url)
        b = client.get_build_by_number(ref.builder_id, ref.build_num)
        # Prefer the eval build (the one that triggers sub-builds).
        steps = client.get_steps(b.buildid)
        if client.extract_buildrequest_ids(steps) or "nix-eval" in url:
            return client, b
    if urls:
        # No eval build with sub-builds found; just return the first.
        ref = parse_buildbot_url(urls[0])
        client = BuildbotClient(ref.base_url)
        if ref.builder_id is not None and ref.build_num is not None:
            return client, client.get_build_by_number(ref.builder_id, ref.build_num)

    msg = (
        f"No buildbot status found on {pr.platform} for "
        f"{pr.owner}/{pr.repo}#{pr.pr_num} ({head_sha[:10]}). "
        f"Either the build has not been scheduled yet or the forge API is unreachable."
    )
    raise BuildbotCheckError(msg)


# --------------------------------------------------------------------------- #
# `pr` (incl. --watch / --failures)
# --------------------------------------------------------------------------- #


def _emit_json(obj: Any) -> None:
    json.dump(obj, sys.stdout, indent=2)
    print()


def _eval_is_bad(ev: EvalBuild) -> bool:
    if ev.build.status and ev.build.status.is_bad:
        return True
    return any(s.build and s.build.status and s.build.status.is_bad for s in ev.sub_builds)


def _watch_until_complete(
    pr: PRInfo, head_sha: str, args: argparse.Namespace
) -> tuple[BuildbotClient, Build]:
    """Poll discovery until the eval build is complete; emit one line per change."""
    last = ""
    while True:
        ts = datetime.now(tz=UTC).strftime("%H:%M:%S")
        try:
            client, build = _discover_eval_build(pr, head_sha)
        except BuildbotCheckError as e:
            if args.json:
                _emit_json({"time": ts, "status": "WAITING", "message": str(e)})
            else:
                print(f"[{ts}] waiting: {e}", flush=True)
            time.sleep(args.interval)
            continue

        ev = client.load_eval_build(build)
        line = (
            f"[{ts}] {build.status_str:<9} #{build.number} "
            f"{build.state_string} ({len(ev.buildrequest_ids)} sub-builds)"
        )
        if args.json:
            _emit_json(
                {
                    "time": ts,
                    "status": build.status_str,
                    "complete": build.complete,
                    "state_string": build.state_string,
                    "build_id": build.buildid,
                    "url": ev.web_url,
                    "sub_builds": len(ev.buildrequest_ids),
                }
            )
        elif line != last:
            print(line, flush=True)
            last = line

        if build.complete:
            return client, build
        time.sleep(args.interval)


def cmd_pr(args: argparse.Namespace) -> int:
    pr = _resolve_pr(args.pr)
    head_sha = _head_sha(pr)

    if args.watch:
        client, build = _watch_until_complete(pr, head_sha, args)
    else:
        client, build = _discover_eval_build(pr, head_sha)

    ev = client.load_eval_build(build)
    ev.sub_builds = client.resolve_sub_builds(ev.buildrequest_ids)

    if args.failures:
        failures = [
            s
            for s in ev.sub_builds
            if (s.build and s.build.status and s.build.status.is_bad) or s.error
        ]
        for s in failures:
            if not s.error:
                client.attach_failure_log(s, tail=args.log_tail)
        if args.json:
            _emit_json(
                {
                    "pr": f"{pr.owner}/{pr.repo}#{pr.pr_num}",
                    "eval_build": ev.web_url,
                    "status": ev.build.status_str,
                    "failures": [s.to_json() for s in failures],
                }
            )
        else:
            print_failures(ev, failures)
        return 1 if failures or _eval_is_bad(ev) else 0

    if args.json:
        _emit_json({"pr": f"{pr.owner}/{pr.repo}#{pr.pr_num}", "eval_build": ev.to_json()})
    else:
        print(f"pr: {pr.owner}/{pr.repo}#{pr.pr_num}")
        print(f"platform: {pr.platform}")
        print()
        print_eval_build(ev)
    return 1 if _eval_is_bad(ev) else 0


# --------------------------------------------------------------------------- #
# argparse
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="buildbot-pr-check",
        description="Inspect Buildbot (buildbot-nix) CI for a PR.",
    )
    p.add_argument("pr", nargs="?", help="PR URL or number (default: current branch)")
    p.add_argument("--watch", action="store_true", help="Poll until the eval build completes")
    p.add_argument("--interval", type=int, default=60, help="Poll interval for --watch (seconds)")
    p.add_argument(
        "--failures",
        action="store_true",
        help="Only failed sub-builds, with attr/error and stdio log tail",
    )
    p.add_argument(
        "--log-tail",
        type=int,
        default=80,
        help="Lines of stdio log to tail with --failures (0=skip)",
    )
    p.add_argument("--json", action="store_true", help="Emit a single JSON document on stdout")
    p.add_argument("--debug", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        sys.exit(cmd_pr(args))
    except BuildbotCheckError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
