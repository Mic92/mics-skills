"""Tag management commands."""

from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.output import emit, emit_json, emit_kv, emit_table, enc, ts


def cmd_tag_list(client: Client, ns: Namespace) -> None:
    """List all tags."""
    result = client.get("/tags")

    def text(data: dict[str, Any]) -> None:
        items = data.get("data", data)
        if not isinstance(items, list):
            emit_json(data)
            return
        emit_table(
            ["ID", "NAME", "CREATED", "UPDATED"],
            [
                [
                    str(t.get("id", "")),
                    str(t.get("name", "")),
                    ts(t.get("createdAt")),
                    ts(t.get("updatedAt")),
                ]
                for t in items
                if isinstance(t, dict)
            ],
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_tag_get(client: Client, ns: Namespace) -> None:
    """Get a tag by ID."""
    result = client.get(f"/tags/{enc(ns.id)}")

    def text(data: dict[str, Any]) -> None:
        emit_kv(
            {
                "ID": str(data.get("id", "")),
                "Name": str(data.get("name", "")),
                "Created": ts(data.get("createdAt")),
                "Updated": ts(data.get("updatedAt")),
            }
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_tag_create(client: Client, ns: Namespace) -> None:
    """Create a tag."""
    body = {"name": ns.name}
    result = client.post("/tags", body)

    def text(data: dict[str, Any]) -> None:
        print(f"Created tag {data.get('name', '')} (id: {data.get('id', '')})")

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_tag_update(client: Client, ns: Namespace) -> None:
    """Update a tag name."""
    body = {"name": ns.name}
    result = client.put(f"/tags/{enc(ns.id)}", body)

    def text(data: dict[str, Any]) -> None:
        print(f"Updated tag to {data.get('name', '')} (id: {data.get('id', '')})")

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_tag_delete(client: Client, ns: Namespace) -> None:
    """Delete a tag by ID."""
    client.delete(f"/tags/{enc(ns.id)}")
    if ns.use_json:
        emit_json({"deleted": True, "id": ns.id})
    else:
        print(f"Deleted tag {ns.id}")
