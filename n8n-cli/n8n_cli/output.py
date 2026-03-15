"""Output formatting helpers."""

import json
import sys
import urllib.parse
from typing import Any

from n8n_cli.errors import InputError


def emit_json(data: Any) -> None:
    """Print JSON to stdout."""
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def emit_kv(pairs: dict[str, str]) -> None:
    """Print key-value pairs, aligned."""
    if not pairs:
        return
    width = max(len(k) for k in pairs) + 1
    for k, v in pairs.items():
        print(f"{k + ':':<{width}} {v}")


def emit_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a compact text table."""
    if not rows:
        print("(none)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        print(fmt.format(*padded))


def emit(data: Any, *, use_json: bool, text_fn: Any = None) -> None:
    """Unified output: JSON if requested, else call text_fn, else fallback to JSON.

    text_fn receives the data and should print text output.
    If text_fn is None or data is not a dict, falls back to JSON.
    """
    if use_json or text_fn is None or not isinstance(data, dict):
        emit_json(data)
    else:
        text_fn(data)


def read_json_input(path: str) -> Any:
    """Read JSON from a file path or '-' for stdin."""
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise InputError(f"File not found: {path}") from None
    except json.JSONDecodeError as e:
        source = "stdin" if path == "-" else path
        raise InputError(f"Invalid JSON in {source}: {e}") from None


def ts(value: str | None) -> str:
    """Format an ISO timestamp to short form, or '-' if missing."""
    if not value:
        return "-"
    return value[:19].replace("T", " ")


def enc(value: str) -> str:
    """URL-encode a path component."""
    return urllib.parse.quote(value, safe="")
