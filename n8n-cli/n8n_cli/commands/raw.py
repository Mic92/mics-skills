"""Raw API command — escape hatch for any endpoint."""

import sys
from argparse import Namespace

from n8n_cli.client import Client
from n8n_cli.errors import InputError
from n8n_cli.output import emit_json, read_json_input


def cmd_raw(client: Client, ns: Namespace) -> None:
    """Make a raw API call."""
    method = ns.method.upper()
    path = ns.path
    if not path.startswith("/"):
        path = f"/{path}"

    body = None
    if ns.file:
        if method in ("GET", "DELETE"):
            print(f"Warning: request body ignored for {method}", file=sys.stderr)
        else:
            body = read_json_input(ns.file)

    methods = {
        "GET": lambda: client.get(path),
        "POST": lambda: client.post(path, body),
        "PUT": lambda: client.put(path, body),
        "PATCH": lambda: client.patch(path, body),
        "DELETE": lambda: client.delete(path),
    }

    fn = methods.get(method)
    if fn is None:
        raise InputError(f"Unsupported HTTP method: {method}")

    result = fn()
    if result is not None:
        emit_json(result)
