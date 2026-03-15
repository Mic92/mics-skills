"""Credential management commands."""

from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.output import emit, emit_json, emit_kv, emit_table, enc, read_json_input, ts
from n8n_cli.strip import CREDENTIAL_WRITABLE, keep_writable


def _text_get(c: dict[str, Any]) -> None:
    emit_kv(
        {
            "ID": str(c.get("id", "")),
            "Name": str(c.get("name", "")),
            "Type": str(c.get("type", "")),
            "Created": ts(c.get("createdAt")),
            "Updated": ts(c.get("updatedAt")),
        }
    )


def _text_mutate(action: str, c: dict[str, Any]) -> None:
    print(f"{action} credential {c.get('name', '')} (id: {c.get('id', '')})")


def cmd_credential_list(client: Client, ns: Namespace) -> None:
    """List all credentials."""
    result = client.get("/credentials")

    def text(data: dict[str, object]) -> None:
        items = data.get("data", data)
        if not isinstance(items, list):
            emit_json(data)
            return
        emit_table(
            ["ID", "NAME", "TYPE", "UPDATED"],
            [
                [
                    str(c.get("id", "")),
                    str(c.get("name", "")),
                    str(c.get("type", "")),
                    ts(c.get("updatedAt")),
                ]
                for c in items
                if isinstance(c, dict)
            ],
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_credential_get(client: Client, ns: Namespace) -> None:
    """Get a credential by ID (metadata only — secrets are not returned)."""
    result = client.get(f"/credentials/{enc(ns.id)}")
    emit(result, use_json=ns.use_json, text_fn=_text_get)


def cmd_credential_create(client: Client, ns: Namespace) -> None:
    """Create a credential from JSON."""
    body = read_json_input(ns.file)
    result = client.post("/credentials", body)
    emit(result, use_json=ns.use_json, text_fn=lambda c: _text_mutate("Created", c))


def cmd_credential_update(client: Client, ns: Namespace) -> None:
    """Update a credential.

    Keeps only fields the public API PATCH endpoint accepts so a
    round-trip get→edit→update works cleanly.
    """
    body = read_json_input(ns.file)
    if isinstance(body, dict):
        body = keep_writable(body, CREDENTIAL_WRITABLE)
    result = client.patch(f"/credentials/{enc(ns.id)}", body)
    emit(result, use_json=ns.use_json, text_fn=lambda c: _text_mutate("Updated", c))


def cmd_credential_delete(client: Client, ns: Namespace) -> None:
    """Delete a credential."""
    result = client.delete(f"/credentials/{enc(ns.id)}")
    if ns.use_json and result is not None:
        emit_json(result)
    else:
        print(f"Deleted credential {ns.id}")


def cmd_credential_test(client: Client, ns: Namespace) -> None:
    """Test a credential by ID."""
    result = client.post(f"/credentials/{enc(ns.id)}/test")

    def text(data: dict[str, object]) -> None:
        status = data.get("status", "unknown")
        msg = data.get("message", "")
        print(f"Test {status}" + (f": {msg}" if msg else ""))

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_credential_schema(client: Client, ns: Namespace) -> None:
    """Get the JSON schema for a credential type."""
    result = client.get(f"/credentials/schema/{enc(ns.type)}")
    emit_json(result)
