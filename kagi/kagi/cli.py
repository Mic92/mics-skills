"""kagi — verb-dispatching CLI (search, summarize).

The `kagi-search` and `kagi-summarize` console_scripts entries call the
``*_entry`` functions below; they prepend the verb to argv and invoke
``main()`` so the original CLIs' invocations keep working.
"""

from __future__ import annotations

import argparse
import sys

from . import search, summarize
from ._auth import KagiError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kagi",
        description="Kagi CLI — search the web or summarize a URL.",
    )
    subparsers = parser.add_subparsers(dest="verb", required=True, metavar="VERB")
    search.add_arguments(
        subparsers.add_parser("search", help="search the web via Kagi"),
    )
    summarize.add_arguments(
        subparsers.add_parser("summarize", help="summarize a URL via Kagi"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse argv and dispatch to a verb."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.verb == "search":
            return search.run(args)
        if args.verb == "summarize":
            return summarize.run(args)
    except KagiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    msg = f"unknown verb: {args.verb!r}"
    raise AssertionError(msg)


def search_entry() -> int:
    """Backward-compat: ``kagi-search ARGS`` -> ``kagi search ARGS``."""
    return main(["search", *sys.argv[1:]])


def summarize_entry() -> int:
    """Backward-compat: ``kagi-summarize ARGS`` -> ``kagi summarize ARGS``."""
    return main(["summarize", *sys.argv[1:]])
