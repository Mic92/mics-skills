"""``kagi search`` — query Kagi via the HTML interface and render results."""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import OpenerDirector, Request

from bs4 import BeautifulSoup, Tag

from ._auth import USER_AGENT, KagiError, build_opener_authed, get_session_token, load_config

logger = logging.getLogger(__name__)

BASE_URL = "https://kagi.com"


def colorize(text: str, color: str = "", *, bold: bool = False, dim: bool = False) -> str:
    """ANSI-colorize text when stdout is a TTY and NO_COLOR is unset."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    codes = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
    }
    escape = codes.get(color.lower(), "") if color else ""
    if bold:
        escape = "\033[1m" + escape
    if dim:
        escape = "\033[2m" + escape
    if not escape:
        return text
    return f"{escape}{text}\033[0m"


def hyperlink(url: str, text: str = "") -> str:
    """OSC 8 terminal hyperlink when output is a TTY."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text or url
    display = text or url
    return f"\033]8;;{url}\033\\{display}\033]8;;\033\\"


@dataclass
class SearchResult:
    """A single search result row."""

    title: str
    url: str
    snippet: str


@dataclass
class QuickAnswer:
    """Kagi's AI-generated answer block, with reference links."""

    html: str
    markdown: str
    raw_text: str
    references: list[dict[str, Any]]


class KagiSearch:
    """Issue Kagi searches over a pre-authenticated cookie session."""

    def __init__(self, opener: OpenerDirector, user_agent: str = USER_AGENT) -> None:
        self.opener = opener
        self.user_agent = user_agent

    def _session_cookie(self) -> str:
        """Return the kagi_session cookie value for the X-Kagi-Authorization header."""
        # OpenerDirector.handlers is public in CPython but missing from typeshed.
        handlers = self.opener.handlers  # type: ignore[attr-defined]
        for handler in handlers:
            jar = getattr(handler, "cookiejar", None)
            if jar is None:
                continue
            for cookie in jar:
                if cookie.name == "kagi_session" and cookie.value:
                    return str(cookie.value)
        return ""

    def search(self, query: str, limit: int = 10, max_retries: int = 5) -> list[SearchResult]:
        """Scrape result rows from Kagi's HTML search page."""
        params = {"q": query}
        search_url = f"{BASE_URL}/html/search?{urlencode(params)}"
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                request = Request(search_url)
                request.add_header("User-Agent", self.user_agent)
                request.add_header(
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8",
                )
                request.add_header("Accept-Language", "en-US,en;q=0.5")
                request.add_header("DNT", "1")
                request.add_header("Connection", "keep-alive")
                request.add_header("Upgrade-Insecure-Requests", "1")

                response = self.opener.open(request, timeout=30)

                final_url = response.geturl()
                if "/signin" in final_url or "/welcome" in final_url:
                    msg = f"authentication failed - redirected to {final_url}"
                    raise KagiError(msg)

                content = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    content = gzip.decompress(content)
                html_content = content.decode("utf-8")
                soup = BeautifulSoup(html_content, "html.parser")

                results_box = soup.find(class_="results-box")
                if not results_box or not isinstance(results_box, Tag):
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    msg = "no results box found on page"
                    raise KagiError(msg)

                results: list[SearchResult] = []
                for result in results_box.find_all(class_="search-result")[:limit]:
                    if not isinstance(result, Tag):
                        continue
                    title_elem = result.find(class_="__sri-title")
                    title = ""
                    if title_elem and isinstance(title_elem, Tag):
                        title_text = title_elem.get_text(separator=" ", strip=True)
                        for sep in (
                            "More results from",
                            "Remove results from",
                            "Open page in",
                        ):
                            if sep in title_text:
                                title_text = title_text.split(sep)[0]
                        title = title_text.strip()

                    url = ""
                    url_box = result.find(class_="__sri-url-box")
                    if url_box and isinstance(url_box, Tag):
                        link = url_box.find("a", href=True)
                        if link and isinstance(link, Tag):
                            href = link.get("href", "")
                            url = str(href) if href else ""

                    desc_elem = result.find(class_="__sri-desc")
                    snippet = (
                        desc_elem.get_text(strip=True)
                        if desc_elem and isinstance(desc_elem, Tag)
                        else ""
                    )
                    if title and url:
                        results.append(SearchResult(title=title, url=url, snippet=snippet))

                if results:
                    return results
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue

            except (URLError, HTTPError) as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                msg = f"request failed: {e}"
                raise KagiError(msg) from e

        return []

    def quick_answer(self, query: str) -> QuickAnswer | None:
        """Fetch Kagi Quick Answer for a query, or None if unavailable."""
        params = {"q": query}
        url = f"{BASE_URL}/mother/context?{urlencode(params)}"
        logger.debug("Quick Answer URL: %s", url)

        try:
            request = Request(url, data=b"", method="POST")
            request.add_header("User-Agent", self.user_agent)
            request.add_header("Accept", "application/vnd.kagi.stream")
            request.add_header("Accept-Language", "en-US,en;q=0.5")
            request.add_header("Accept-Encoding", "gzip, deflate")
            request.add_header("Referer", f"{BASE_URL}/search?{urlencode(params)}")
            request.add_header("Origin", BASE_URL)
            request.add_header("Connection", "keep-alive")
            request.add_header("Content-Length", "0")
            cookie = self._session_cookie()
            if cookie:
                request.add_header("X-Kagi-Authorization", cookie)

            response = self.opener.open(request, timeout=30)
            final_url = response.geturl()
            if "/signin" in final_url or "/welcome" in final_url:
                msg = f"authentication failed - redirected to {final_url}"
                raise KagiError(msg)

            content = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                content = gzip.decompress(content)
            text = content.decode("utf-8")

            final_data: dict[str, Any] | None = None
            for line in text.strip().split("\n"):
                line_stripped = line.strip()
                if not line_stripped.startswith("new_message.json:"):
                    continue
                payload = line_stripped[len("new_message.json:") :]
                try:
                    final_data, _ = json.JSONDecoder().raw_decode(payload)
                except json.JSONDecodeError as e:
                    logger.debug("failed to parse new_message JSON: %s", e)

            if not final_data:
                return None

            markdown = str(final_data.get("md", ""))
            html = str(final_data.get("reply", ""))
            references_md = str(final_data.get("references_md", ""))
            references: list[dict[str, Any]] = []
            if references_md:
                ref_pattern = r"\[\^\d+\]:\s*\[([^\]]+)\]\((.+?)\)\s*\((\d+)%\)"
                for match in re.finditer(ref_pattern, references_md):
                    references.append(
                        {
                            "title": match.group(1),
                            "url": match.group(2),
                            "contribution": f"{match.group(3)}%",
                        },
                    )
            if not html and not markdown:
                return None
            return QuickAnswer(
                html=html,
                markdown=markdown,
                raw_text=markdown,
                references=references,
            )

        except KagiError:
            raise
        except (URLError, HTTPError, OSError) as e:
            logger.debug("Quick Answer error: %s: %s", type(e).__name__, e)
            return None


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register `kagi search` flags onto its subparser."""
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument(
        "-n",
        "--num-results",
        type=int,
        default=3,
        help="Number of link results (default: 3)",
    )
    parser.add_argument(
        "-l",
        "--links",
        action="store_true",
        help="Show search result links (hidden by default)",
    )
    parser.add_argument("-t", "--token", help="Session token (overrides config)")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug logging to stderr",
    )


def run(args: argparse.Namespace) -> int:
    """Execute the search verb. Returns process exit code."""
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    if not args.query:
        if sys.stdin.isatty():
            print("error: no query provided", file=sys.stderr)
            return 2
        args.query = sys.stdin.read().strip()

    if args.token:
        opener = build_opener_authed(args.token)
    else:
        cfg_path = Path(args.config) if args.config else None
        cfg = load_config(cfg_path)
        opener = build_opener_authed(get_session_token(cfg))

    client = KagiSearch(opener)
    results: list[SearchResult] = []
    if args.links:
        results = client.search(args.query, limit=args.num_results)
    qa = client.quick_answer(args.query)

    if args.json:
        out: dict[str, Any] = {
            "results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
        }
        if qa:
            out["quick_answer"] = {
                "markdown": qa.markdown,
                "raw_text": qa.raw_text,
                "references": qa.references,
            }
        print(json.dumps(out, indent=2))
    else:
        _render_human(qa, results)

    if not qa and not results and not args.json:
        print(colorize("No results found", color="red"), file=sys.stderr)
    return 0


def _render_human(qa: QuickAnswer | None, results: list[SearchResult]) -> None:
    """Pretty-print Quick Answer + result list to stdout."""
    if qa:
        print(f"\n{colorize('Quick Answer', color='cyan', bold=True)}")
        print(colorize("─" * 80, color="cyan", dim=True))
        if qa.raw_text:
            print(qa.raw_text)
        elif qa.markdown:
            print(qa.markdown)
        if qa.references:
            print()
            print(colorize("References:", color="cyan", dim=True))
            for i, ref in enumerate(qa.references[:5], 1):
                ref_num = colorize(f"[{i}]", color="cyan", dim=True)
                ref_title = ref.get("title", "")
                ref_url = ref.get("url", "")
                if ref_title and ref_url:
                    title_styled = hyperlink(ref_url, colorize(ref_title, color="blue"))
                    url_styled = hyperlink(ref_url, colorize(ref_url, color="green", dim=True))
                    print(f"  {ref_num} {title_styled}")
                    print(f"      {url_styled}")
        print(colorize("─" * 80, color="cyan", dim=True))

    if results:
        if qa:
            print()
        for i, result in enumerate(results, 1):
            number = colorize(f"{i}.", color="yellow", bold=True)
            title_styled = hyperlink(result.url, colorize(result.title, color="blue", bold=True))
            url_styled = hyperlink(result.url, colorize(result.url, color="green"))
            print(f"\n{number} {title_styled}")
            print(f"   {url_styled}")
            if result.snippet:
                print(f"   {colorize(result.snippet, dim=True)}")
