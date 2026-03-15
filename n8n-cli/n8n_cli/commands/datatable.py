"""Data table management commands."""

import json
import urllib.parse
from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.errors import InputError
from n8n_cli.output import emit, emit_json, emit_kv, emit_table, enc, read_json_input, ts


# ---------------------------------------------------------------------------
# Table-level commands
# ---------------------------------------------------------------------------


def cmd_datatable_list(client: Client, ns: Namespace) -> None:
    """List all data tables."""
    params: dict[str, str] = {}
    if ns.filter:
        params["filter"] = ns.filter
    if ns.sort:
        params["sortBy"] = ns.sort
    if ns.limit is not None:
        params["limit"] = str(ns.limit)

    qs = urllib.parse.urlencode(params)
    path = f"/data-tables?{qs}" if qs else "/data-tables"
    result = client.get(path)

    def text(data: dict[str, Any]) -> None:
        items = data.get("data", data)
        if not isinstance(items, list):
            emit_json(data)
            return
        emit_table(
            ["ID", "NAME", "COLUMNS", "UPDATED"],
            [
                [
                    str(t.get("id", "")),
                    str(t.get("name", "")),
                    str(len(t.get("columns", []))),
                    ts(t.get("updatedAt")),
                ]
                for t in items
                if isinstance(t, dict)
            ],
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_datatable_get(client: Client, ns: Namespace) -> None:
    """Get a data table by ID (includes column definitions)."""
    result = client.get(f"/data-tables/{enc(ns.id)}")

    def text(data: dict[str, Any]) -> None:
        cols = data.get("columns", [])
        col_strs = [f"{c.get('name', '')}:{c.get('type', '')}" for c in cols if isinstance(c, dict)]
        emit_kv(
            {
                "ID": str(data.get("id", "")),
                "Name": str(data.get("name", "")),
                "Columns": ", ".join(col_strs) if col_strs else "-",
                "Created": ts(data.get("createdAt")),
                "Updated": ts(data.get("updatedAt")),
            }
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_datatable_create(client: Client, ns: Namespace) -> None:
    """Create a data table from JSON."""
    body = read_json_input(ns.file)
    result = client.post("/data-tables", body)

    def text(data: dict[str, Any]) -> None:
        print(f"Created table {data.get('name', '')} (id: {data.get('id', '')})")

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_datatable_update(client: Client, ns: Namespace) -> None:
    """Rename a data table."""
    result = client.patch(f"/data-tables/{enc(ns.id)}", {"name": ns.name})

    def text(data: dict[str, Any]) -> None:
        print(f"Renamed table to {data.get('name', '')} (id: {data.get('id', '')})")

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_datatable_delete(client: Client, ns: Namespace) -> None:
    """Delete a data table (and all its rows)."""
    client.delete(f"/data-tables/{enc(ns.id)}")

    def text(_: dict[str, Any]) -> None:
        print(f"Deleted table {ns.id}")

    emit({"deleted": True, "id": ns.id}, use_json=ns.use_json, text_fn=text)


# ---------------------------------------------------------------------------
# Row-level commands
# ---------------------------------------------------------------------------


def cmd_datatable_rows(client: Client, ns: Namespace) -> None:
    """List rows from a data table."""
    params: dict[str, str] = {}
    if ns.filter:
        params["filter"] = ns.filter
    if ns.sort:
        params["sortBy"] = ns.sort
    if ns.search:
        params["search"] = ns.search
    if ns.limit is not None:
        params["limit"] = str(ns.limit)

    qs = urllib.parse.urlencode(params)
    path = f"/data-tables/{enc(ns.id)}/rows"
    if qs:
        path += f"?{qs}"
    result = client.get(path)

    def text(data: dict[str, Any]) -> None:
        items = data.get("data", data)
        if not isinstance(items, list):
            emit_json(data)
            return
        if not items:
            print("(no rows)")
            return
        cols = list(items[0].keys())
        emit_table(
            [c.upper() for c in cols],
            [[str(row.get(c, "")) for c in cols] for row in items if isinstance(row, dict)],
        )

    emit(result, use_json=ns.use_json, text_fn=text)


def cmd_datatable_insert(client: Client, ns: Namespace) -> None:
    """Insert rows into a data table."""
    body = read_json_input(ns.file)

    if isinstance(body, list):
        body = {"data": body, "returnType": ns.return_type}
    elif isinstance(body, dict):
        body.setdefault("returnType", ns.return_type)
    else:
        raise InputError('Insert JSON must be an array of rows or {"data": [...]}')

    result = client.post(f"/data-tables/{enc(ns.id)}/rows", body)
    emit_json(result)


def cmd_datatable_update_rows(client: Client, ns: Namespace) -> None:
    """Update rows matching a filter."""
    body = read_json_input(ns.file)
    result = client.patch(f"/data-tables/{enc(ns.id)}/rows/update", body)
    emit_json(result)


def cmd_datatable_upsert(client: Client, ns: Namespace) -> None:
    """Upsert a row (update if filter matches, insert otherwise)."""
    body = read_json_input(ns.file)
    result = client.post(f"/data-tables/{enc(ns.id)}/rows/upsert", body)
    emit_json(result)


def cmd_datatable_delete_rows(client: Client, ns: Namespace) -> None:
    """Delete rows matching a filter."""
    try:
        json.loads(ns.filter)
    except json.JSONDecodeError as e:
        raise InputError(f"Invalid filter JSON: {e}") from None

    params: dict[str, str] = {"filter": ns.filter}
    if ns.return_data:
        params["returnData"] = "true"
    if ns.dry_run:
        params["dryRun"] = "true"

    qs = urllib.parse.urlencode(params)
    result = client.delete(f"/data-tables/{enc(ns.id)}/rows/delete?{qs}")
    emit_json(result)
