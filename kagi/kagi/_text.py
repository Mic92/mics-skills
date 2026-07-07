"""Shared HTML/Markdown -> plain-text helpers.

Used by both the ``search`` and ``summarize`` verbs, so it lives in a neutral
module rather than inside either verb (avoids one verb importing another).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    """Convert HTML to plain text, preserving paragraph and list breaks."""

    _BLOCK = frozenset({"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag == "li":
            self._parts.append("- ")
        elif tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            self._parts.append("\n\n")
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        out = "".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", out).strip()


def html_to_text(html: str) -> str:
    """Convert HTML to plain text via the stdlib html.parser."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


# Markdown is regular enough for regex stripping; HTML gets the parser above.
_MD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"```[a-zA-Z0-9_+-]*\n"), ""),
    (re.compile(r"```"), ""),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"!\[[^\]]*\]\([^)]+\)"), ""),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r"\1 (\2)"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"\*([^*\n]+)\*"), r"\1"),
    (re.compile(r"_([^_\n]+)_"), r"\1"),
    (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), "- "),
    (re.compile(r"^\s*\d+\.\s+", re.MULTILINE), ""),
    (re.compile(r"^>\s*", re.MULTILINE), ""),
]


def markdown_to_text(md: str) -> str:
    """Strip common Markdown formatting to leave readable plain prose."""
    s = md
    for pattern, repl in _MD_PATTERNS:
        s = pattern.sub(repl, s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()
