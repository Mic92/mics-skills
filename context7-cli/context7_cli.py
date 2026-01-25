#!/usr/bin/env python3
"""
context7-cli - CLI for the Context7 documentation API

Get up-to-date library documentation and code examples for LLM prompts.

Usage:
    context7-cli search <library_name> <query>       Search for libraries
    context7-cli search --json <library_name> <query>  Search (JSON output)
    context7-cli docs <library_id> <query>           Get documentation context
    context7-cli docs --json <library_id> <query>    Get docs (JSON output)
    context7-cli -k <key> search ...                 Use explicit API key
    context7-cli --help                              Show this help

Options:
    -k, --api-key KEY    API key (overrides config and environment)
    -c, --config PATH    Config file path
    --json               Output as JSON

Environment:
    CONTEXT7_API_KEY    API key for higher rate limits
                        Get one at: https://context7.com/dashboard

Config file (~/.config/context7/config.json):
    {
        "password_command": "rbw get context7-api-key",
        "api_key": "ctx7sk..."
    }

    password_command: Shell command to retrieve API key (preferred)
    api_key: Direct API key (fallback if no password_command)

Examples:
    context7-cli search react "how to use hooks"
    context7-cli search --json nextjs "middleware"
    context7-cli docs /facebook/react "useState examples"
    context7-cli docs /vercel/next.js/v14.3.0 "middleware authentication"
    context7-cli -k ctx7sk_xxx docs /vercel/next.js "routing"
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, NoReturn

CONTEXT7_API_BASE_URL = os.environ.get("CONTEXT7_API_URL", "https://context7.com/api")
ALLOWED_SCHEMES = ("https",)


@dataclass
class Config:
    """Runtime configuration."""

    api_key: str | None = None


# Runtime config instance
config = Config()


@dataclass
class SearchResult:
    """Library search result from Context7 API."""

    id: str
    title: str
    description: str
    branch: str
    last_update_date: str
    state: str
    total_tokens: int
    total_snippets: int
    stars: int | None = None
    trust_score: int | None = None
    benchmark_score: float | None = None
    versions: list[str] | None = None


@dataclass
class SearchResponse:
    """Response from library search endpoint."""

    results: list[SearchResult]
    error: str | None = None


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from file."""
    if config_path:
        config_file = Path(config_path)
    else:
        config_file = Path.home() / ".config" / "context7" / "config.json"

    if not config_file.exists():
        return {}

    with config_file.open() as f:
        data: dict[str, Any] = json.load(f)
        return data


def get_api_key_from_command(command: str) -> str | None:
    """Execute password command to retrieve API key."""
    try:
        # Using shell=True is intentional here - the command comes from user's
        # config file, similar to how kagi-search handles password_command.
        # The user controls both the config and the command being executed.
        result = subprocess.run(  # noqa: S602
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError as e:
        print(f"Warning: password_command failed: {e}", file=sys.stderr)
        if e.stderr:
            print(f"  stderr: {e.stderr.strip()}", file=sys.stderr)
        return None


def resolve_api_key(cli_key: str | None = None, config_path: str | None = None) -> str | None:
    """
    Resolve API key from multiple sources (in priority order):
    1. CLI argument (-k/--api-key)
    2. Environment variable (CONTEXT7_API_KEY)
    3. Config file password_command
    4. Config file api_key
    """
    # 1. CLI argument takes precedence
    if cli_key:
        return cli_key

    # 2. Environment variable
    env_key = os.environ.get("CONTEXT7_API_KEY")
    if env_key:
        return env_key

    # 3 & 4. Config file
    file_config = load_config(config_path)

    # 3. password_command (preferred - more secure)
    password_cmd = file_config.get("password_command")
    if password_cmd and isinstance(password_cmd, str):
        key = get_api_key_from_command(password_cmd)
        if key:
            return key

    # 4. Direct api_key in config (fallback)
    config_key = file_config.get("api_key")
    if isinstance(config_key, str) and config_key:
        result: str = config_key
        return result

    return None


def validate_url(url: str) -> None:
    """Validate URL uses allowed schemes only."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        msg = f"Invalid URL scheme: {parsed.scheme}. Only HTTPS allowed."
        raise ValueError(msg)


def make_headers() -> dict[str, str]:
    """Generate request headers including optional API key."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "context7-cli/1.0",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def parse_error_response(response_body: bytes, status: int) -> str:
    """Parse error response, extracting server message if available."""
    try:
        data = json.loads(response_body.decode("utf-8"))
        if "message" in data and isinstance(data["message"], str):
            return data["message"]
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    if status == 429:
        if config.api_key:
            return "Rate limited. Upgrade at https://context7.com/plans for higher limits."
        return "Rate limited. Get a free API key at https://context7.com/dashboard"
    if status == 404:
        return "Library not found. Check the library ID."
    if status == 401:
        return "Invalid API key. Keys should start with 'ctx7sk' prefix."
    return f"Request failed with status {status}"


def search_libraries(library_name: str, query: str) -> SearchResponse:
    """
    Search for libraries matching the given query.

    Args:
        library_name: The library name to search for
        query: User's question/task for relevance ranking

    Returns:
        SearchResponse with results or error
    """
    params = urllib.parse.urlencode({"libraryName": library_name, "query": query})
    url = f"{CONTEXT7_API_BASE_URL}/v2/libs/search?{params}"
    validate_url(url)

    request = urllib.request.Request(url, headers=make_headers())  # noqa: S310

    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
            results = [
                SearchResult(
                    id=r["id"],
                    title=r["title"],
                    description=r.get("description", ""),
                    branch=r.get("branch", ""),
                    last_update_date=r.get("lastUpdateDate", ""),
                    state=r.get("state", ""),
                    total_tokens=r.get("totalTokens", 0),
                    total_snippets=r.get("totalSnippets", 0),
                    stars=r.get("stars"),
                    trust_score=r.get("trustScore"),
                    benchmark_score=r.get("benchmarkScore"),
                    versions=r.get("versions"),
                )
                for r in data.get("results", [])
            ]
            return SearchResponse(results=results)
    except urllib.error.HTTPError as e:
        error_body = e.read()
        error_msg = parse_error_response(error_body, e.code)
        return SearchResponse(results=[], error=error_msg)
    except urllib.error.URLError as e:
        return SearchResponse(results=[], error=f"Network error: {e.reason}")
    except TimeoutError:
        return SearchResponse(results=[], error="Request timed out")


def get_documentation(library_id: str, query: str, output_format: str = "txt") -> str:
    """
    Fetch documentation context for a library.

    Args:
        library_id: Context7-compatible library ID (e.g., /vercel/next.js)
        query: Natural language query for relevant docs
        output_format: Response format ('txt' or 'json')

    Returns:
        Documentation text or JSON, or error message
    """
    params = urllib.parse.urlencode(
        {"libraryId": library_id, "query": query, "type": output_format}
    )
    url = f"{CONTEXT7_API_BASE_URL}/v2/context?{params}"
    validate_url(url)

    headers = make_headers()
    if output_format == "txt":
        headers["Accept"] = "text/plain"

    request = urllib.request.Request(url, headers=headers)  # noqa: S310

    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            content: str = response.read().decode("utf-8")
            return content
    except urllib.error.HTTPError as e:
        error_body = e.read()
        return f"Error: {parse_error_response(error_body, e.code)}"
    except urllib.error.URLError as e:
        return f"Error: Network error: {e.reason}"
    except TimeoutError:
        return "Error: Request timed out"


def format_search_results(response: SearchResponse, as_json: bool = False) -> str:
    """Format search results for display."""
    if as_json:
        return json.dumps(
            {
                "results": [asdict(r) for r in response.results],
                "error": response.error,
            },
            indent=2,
        )

    if response.error:
        return f"Error: {response.error}"

    if not response.results:
        return "No libraries found matching your query."

    lines = [f"Found {len(response.results)} libraries:\n"]

    for r in response.results:
        stars = f"⭐ {r.stars:,}" if r.stars else ""
        snippets = f"{r.total_snippets} snippets" if r.total_snippets else ""
        tokens = f"{r.total_tokens:,} tokens" if r.total_tokens else ""

        lines.append(f"  {r.id}")
        lines.append(f"    {r.title}: {r.description}")

        meta = [s for s in [stars, snippets, tokens] if s]
        if meta:
            lines.append(f"    {' | '.join(meta)}")

        if r.versions:
            lines.append(f"    Versions: {', '.join(r.versions[:5])}")

        lines.append("")

    return "\n".join(lines)


def print_usage() -> NoReturn:
    """Print usage information and exit."""
    print(__doc__)
    sys.exit(0)


def print_error(msg: str) -> NoReturn:
    """Print error message and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    print("Run 'context7-cli --help' for usage.", file=sys.stderr)
    sys.exit(1)


@dataclass
class ParsedArgs:
    """Parsed command-line arguments."""

    command: str
    json_output: bool
    api_key: str | None
    config_path: str | None
    remaining: list[str]


def parse_args(args: list[str]) -> ParsedArgs:
    """
    Parse command and flags from args.

    Returns:
        ParsedArgs with command, flags, and remaining arguments
    """
    json_output = False
    api_key = None
    config_path = None
    remaining = []
    command = ""

    i = 0
    while i < len(args):
        arg = args[i]

        if arg in ("-k", "--api-key"):
            if i + 1 >= len(args):
                print_error(f"{arg} requires a value")
            api_key = args[i + 1]
            i += 2
        elif arg in ("-c", "--config"):
            if i + 1 >= len(args):
                print_error(f"{arg} requires a value")
            config_path = args[i + 1]
            i += 2
        elif arg == "--json":
            json_output = True
            i += 1
        elif arg in ("--help", "-h", "help"):
            print_usage()
        elif not command and not arg.startswith("-"):
            command = arg
            i += 1
        else:
            remaining.append(arg)
            i += 1

    return ParsedArgs(
        command=command,
        json_output=json_output,
        api_key=api_key,
        config_path=config_path,
        remaining=remaining,
    )


def main() -> None:
    """Main entry point."""
    args = sys.argv[1:]

    if not args:
        print_usage()

    parsed = parse_args(args)

    # Resolve API key from all sources
    config.api_key = resolve_api_key(parsed.api_key, parsed.config_path)

    if not parsed.command:
        print_error("No command specified")

    if parsed.command == "search":
        if len(parsed.remaining) < 2:
            print_error("search requires <library_name> and <query>")
        library_name = parsed.remaining[0]
        query = " ".join(parsed.remaining[1:])
        response = search_libraries(library_name, query)
        print(format_search_results(response, as_json=parsed.json_output))

    elif parsed.command == "docs":
        if len(parsed.remaining) < 2:
            print_error("docs requires <library_id> and <query>")
        library_id = parsed.remaining[0]
        # Ensure library_id starts with /
        if not library_id.startswith("/"):
            library_id = "/" + library_id
        query = " ".join(parsed.remaining[1:])
        output_format = "json" if parsed.json_output else "txt"
        output = get_documentation(library_id, query, output_format)
        print(output)

    else:
        print_error(f"Unknown command: {parsed.command}")


if __name__ == "__main__":
    main()
