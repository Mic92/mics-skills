"""Workflow management commands."""

import urllib.parse
from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.errors import InputError
from n8n_cli.output import emit, emit_json, emit_kv, emit_table, enc, read_json_input, ts


def _text_summary(wf: dict[str, Any]) -> None:
    """Print a compact workflow summary."""
    tags = wf.get("tags", [])
    tag_str = ", ".join(t.get("name", "") for t in tags if isinstance(t, dict)) if tags else "-"
    emit_kv(
        {
            "ID": str(wf.get("id", "")),
            "Name": str(wf.get("name", "")),
            "Active": "yes" if wf.get("active") else "no",
            "Nodes": str(len(wf.get("nodes", []))),
            "Tags": tag_str,
            "Updated": ts(wf.get("updatedAt")),
        }
    )


def cmd_workflow_list(client: Client, ns: Namespace) -> None:
    """List all workflows with optional filters."""
    params: dict[str, str] = {}
    if ns.active is not None:
        params["active"] = "true" if ns.active else "false"
    if ns.tags:
        params["tags"] = ns.tags
    if ns.name:
        params["name"] = ns.name
    if ns.limit is not None:
        params["limit"] = str(ns.limit)

    qs = urllib.parse.urlencode(params)
    path = f"/workflows?{qs}" if qs else "/workflows"
    result = client.get(path)

    def text(data: dict[str, Any]) -> None:
        items = data.get("data", data)
        if not isinstance(items, list):
            emit_json(data)
            return
        emit_table(
            ["ID", "NAME", "ACTIVE", "TAGS", "UPDATED"],
            [
                [
                    str(w.get("id", "")),
                    str(w.get("name", "")),
                    "yes" if w.get("active") else "no",
                    ", ".join(
                        t.get("name", "") for t in (w.get("tags") or []) if isinstance(t, dict)
                    )
                    or "-",
                    ts(w.get("updatedAt")),
                ]
                for w in items
                if isinstance(w, dict)
            ],
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_workflow_get(client: Client, ns: Namespace) -> None:
    """Get a workflow by ID — always outputs full JSON for round-trip editing."""
    result = client.get(f"/workflows/{enc(ns.id)}")
    emit_json(result)


def cmd_workflow_create(client: Client, ns: Namespace) -> None:
    """Create a workflow from a JSON definition."""
    body = read_json_input(ns.file)
    if not isinstance(body, dict):
        raise InputError("Workflow JSON must be an object, not an array or scalar")
    result = client.post("/workflows", body)

    def text(data: dict[str, Any]) -> None:
        print(f"Created workflow {data.get('name', '')} (id: {data.get('id', '')})")

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_workflow_update(client: Client, ns: Namespace) -> None:
    """Update a workflow from a full JSON definition.

    Strips id, createdAt, updatedAt, tags, shared, pinData before PUT.
    """
    body = read_json_input(ns.file)
    if not isinstance(body, dict):
        raise InputError("Workflow JSON must be an object, not an array or scalar")
    for key in ("id", "createdAt", "updatedAt", "tags", "shared", "pinData"):
        body.pop(key, None)
    result = client.put(f"/workflows/{enc(ns.id)}", body)
    emit(result, use_json=ns.use_json, text_fn=_text_summary)


def cmd_workflow_delete(client: Client, ns: Namespace) -> None:
    """Delete a workflow by ID."""
    result = client.delete(f"/workflows/{enc(ns.id)}")

    def text(data: dict[str, Any]) -> None:
        name = data.get("name", "") if isinstance(data, dict) else ""
        print(f"Deleted workflow {name} (id: {ns.id})")

    emit(result, use_json=ns.use_json, text_fn=text)


def _cmd_toggle(client: Client, ns: Namespace, *, action: str, endpoint: str) -> None:
    """Activate or deactivate a workflow via POST."""
    result = client.post(f"/workflows/{enc(ns.id)}/{endpoint}")

    def text(data: dict[str, object]) -> None:
        past = f"{action}d" if action.endswith("e") else f"{action}ed"
        print(f"{past.capitalize()} workflow {data.get('name', '')} (id: {data.get('id', ns.id)})")

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_workflow_activate(client: Client, ns: Namespace) -> None:
    """Activate a workflow."""
    _cmd_toggle(client, ns, action="activate", endpoint="activate")


def cmd_workflow_deactivate(client: Client, ns: Namespace) -> None:
    """Deactivate a workflow."""
    _cmd_toggle(client, ns, action="deactivate", endpoint="deactivate")
