"""Workflow management commands."""

from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.errors import InputError
from n8n_cli.output import emit, emit_json, emit_kv, enc, read_json_input, ts


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


def cmd_workflow_get(client: Client, ns: Namespace) -> None:
    """Get a workflow by ID — always outputs full JSON for round-trip editing."""
    result = client.get(f"/workflows/{enc(ns.id)}")
    emit_json(result)


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
