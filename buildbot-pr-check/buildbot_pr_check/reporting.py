"""Human/agent-readable rendering of EvalBuild / SubBuild results.

Output is deliberately plain ``key: value`` blocks separated by blank lines so
an LLM (or ``grep``) can parse it without ANSI/emoji noise. For fully
structured output use ``--json``.
"""

from collections import Counter

from .buildbot_api import EvalBuild, SubBuild


def _kv(key: str, value: object, indent: int = 0) -> None:
    pad = " " * indent
    print(f"{pad}{key}: {value}")


def print_eval_build(ev: EvalBuild) -> None:
    b = ev.build
    print("eval_build:")
    _kv("url", ev.web_url, 2)
    _kv("build_id", b.buildid, 2)
    _kv("status", b.status_str, 2)
    _kv("complete", b.complete, 2)
    _kv("state", b.state_string, 2)

    if not ev.sub_builds:
        _kv("sub_builds", f"{len(ev.buildrequest_ids)} (not resolved)", 2)
        return

    counts: Counter[str] = Counter(s.status_str for s in ev.sub_builds)
    summary = " ".join(f"{k}={n}" for k, n in sorted(counts.items()))
    _kv("sub_builds", f"{len(ev.sub_builds)} ({summary})", 2)
    print()

    width = max((len(s.attr or "") for s in ev.sub_builds), default=0)
    print("sub_builds:")
    for s in ev.sub_builds:
        name = s.attr or f"buildrequest/{s.buildrequest_id}"
        state = s.build.state_string if s.build else ""
        print(f"  - attr: {name:<{width}}  status: {s.status_str:<9}  state: {state}")


def print_failures(ev: EvalBuild, failures: list[SubBuild]) -> None:
    print("eval_build:")
    _kv("url", ev.web_url, 2)
    _kv("status", ev.build.status_str, 2)
    _kv("state", ev.build.state_string, 2)
    _kv("failed_sub_builds", len(failures), 2)

    for s in failures:
        print()
        print("failure:")
        _kv("attr", s.attr or f"buildrequest/{s.buildrequest_id}", 2)
        _kv("status", s.status_str, 2)
        if s.build:
            _kv("build_id", s.build.buildid, 2)
            _kv("state", s.build.state_string, 2)
        if s.log_url:
            _kv("log_url", s.log_url, 2)
        if s.error:
            print("  error: |")
            for line in s.error.splitlines():
                print(f"    {line}")
        if s.log_tail:
            print("  log_tail: |")
            for line in s.log_tail.splitlines():
                print(f"    {line}")
