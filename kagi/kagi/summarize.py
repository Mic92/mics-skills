"""``kagi summarize`` — Kagi Universal Summarizer for a known URL.

Hits the same internal ``/mother/summary_labs`` endpoint the web UI uses,
authenticated via the shared session in ``_auth.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import OpenerDirector, Request

from ._auth import BASE_URL, KagiError, authed_opener
from ._text import html_to_text, markdown_to_text

logger = logging.getLogger(__name__)


def summarize(
    opener: OpenerDirector,
    url: str,
    summary_type: str = "summary",
    target_language: str = "EN",
) -> dict[str, Any]:
    """POST to Kagi's summarizer; ``summary_type`` is ``summary`` (paragraph) or ``takeaway`` (bullets)."""
    body = urlencode(
        {
            "url": url,
            "summary_type": summary_type,
            "target_language": target_language,
        },
    ).encode()
    req = Request(
        f"{BASE_URL}/mother/summary_labs",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/summarizer",
        },
        method="POST",
    )
    try:
        resp = opener.open(req, timeout=120)
    except (HTTPError, URLError) as e:
        msg = f"summarize request failed: {e}"
        raise KagiError(msg) from e
    raw = resp.read().decode(errors="replace")
    try:
        result: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        msg = f"non-JSON response: {raw[:300]}"
        raise KagiError(msg) from e
    return result


def render(data: dict[str, Any], fmt: str) -> str:
    """Render the Kagi response in ``json``, ``markdown``, or ``text`` form."""
    if fmt == "json":
        return json.dumps(data, indent=2)

    output_data = data.get("output_data") or {}
    md_field = output_data.get("markdown") or ""
    output_text = data.get("output_text", "")

    if fmt == "text":
        if md_field:
            return markdown_to_text(md_field)
        return html_to_text(output_text)

    if md_field:
        return md_field
    return html_to_text(output_text)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register `kagi summarize` flags onto its subparser."""
    parser.add_argument("url", help="URL to summarize")
    parser.add_argument(
        "--takeaway",
        action="store_true",
        help="Bullet-list format (default: paragraph summary)",
    )
    parser.add_argument(
        "--language",
        default="EN",
        help="Target language (default: EN)",
    )
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument(
        "-j",
        "--json",
        action="store_const",
        const="json",
        dest="format",
        help="Output raw JSON response",
    )
    fmt.add_argument(
        "--text",
        action="store_const",
        const="text",
        dest="format",
        help="Output plain text (strips markdown and HTML)",
    )
    fmt.add_argument(
        "--markdown",
        action="store_const",
        const="markdown",
        dest="format",
        help="Output markdown (default)",
    )
    parser.set_defaults(format="markdown")


def run(args: argparse.Namespace) -> int:
    """Execute the summarize verb."""
    opener = authed_opener()
    summary_type = "takeaway" if args.takeaway else "summary"
    data = summarize(
        opener,
        args.url,
        summary_type=summary_type,
        target_language=args.language,
    )

    if data.get("error"):
        print(f"error: kagi: {data.get('output_text', 'unknown')}", file=sys.stderr)
        return 1

    print(render(data, args.format))

    # Stats footer (stderr so pipelines stay clean).
    stats = (data.get("output_data") or {}).get("word_stats") or {}
    if stats:
        print(
            f"\n[{stats.get('n_words', '?')} words, "
            f"{stats.get('n_pages', '?')} pages, "
            f"~{stats.get('time_saved', '?')} min saved]",
            file=sys.stderr,
        )
    return 0
