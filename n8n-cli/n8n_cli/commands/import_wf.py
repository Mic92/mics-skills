"""Import command — download workflows from n8n server to local JSON files."""

import json
import os
import re
from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.output import atomic_write, enc


def _slugify(name: str) -> str:
    """Convert a workflow name to a filesystem-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:80]


def _generate_filename(wf_id: str, name: str) -> str:
    """Generate a filename like 'daily-report_wf-1.json'."""
    slug = _slugify(name)
    if slug:
        return f"{slug}_{wf_id}.json"
    return f"{wf_id}.json"


def _build_local_index(directory: str) -> dict[str, str]:
    """Build a mapping of workflow ID → file path for all JSON files in directory."""
    index: dict[str, str] = {}
    if not os.path.isdir(directory):
        return index
    for name in os.listdir(directory):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("id"):
                index[data["id"]] = path
        except (json.JSONDecodeError, OSError):
            continue
    return index


def _should_update(local_updated: str | None, remote_updated: str | None) -> bool:
    """Return True if remote is newer than local."""
    if not local_updated:
        return True
    if not remote_updated:
        return False
    return remote_updated > local_updated


def _fetch_all_workflows(client: Client, ids: list[str] | None) -> list[dict[str, Any]]:
    """Fetch all workflows from server, with optional ID filter and pagination."""
    all_wfs: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        params = "limit=100"
        if cursor:
            params += f"&cursor={enc(cursor)}"
        result = client.get(f"/workflows?{params}")
        if not isinstance(result, dict):
            break

        items = result.get("data", [])
        if not isinstance(items, list):
            break

        for wf in items:
            if not isinstance(wf, dict):
                continue
            if ids and wf.get("id") not in ids:
                continue
            all_wfs.append(wf)

        next_cursor = result.get("nextCursor")
        if not next_cursor:
            break
        cursor = next_cursor

    return all_wfs


def cmd_import(client: Client, ns: Namespace) -> None:
    """Import workflows from n8n server to local JSON files."""
    directory = ns.dir

    # Parse IDs filter
    ids: list[str] | None = None
    if ns.ids:
        ids = [s.strip() for s in ns.ids.split(",") if s.strip()]

    # Fetch workflows
    workflows = _fetch_all_workflows(client, ids)
    if not workflows:
        print("No workflows found.")
        return

    os.makedirs(directory, exist_ok=True)
    local_index = _build_local_index(directory)

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for wf in workflows:
        wf_id = wf.get("id", "")
        wf_name = wf.get("name", "")
        remote_updated = wf.get("updatedAt")

        if not wf_id:
            print(f"  skip: workflow with empty ID ({wf_name})")
            skipped += 1
            continue

        # Find existing local file or generate new path
        existing = local_index.get(wf_id)
        if existing:
            # Check if update needed
            try:
                with open(existing) as f:
                    local_data = json.load(f)
                local_updated = (
                    local_data.get("updatedAt") if isinstance(local_data, dict) else None
                )
                if not _should_update(local_updated, remote_updated):
                    if not ns.dry_run:
                        print(f"  skip: {os.path.basename(existing)} (up to date)")
                    skipped += 1
                    continue
            except (json.JSONDecodeError, OSError):
                pass  # Treat as needs update

            target_path = existing
            op = "update"
        else:
            target_path = os.path.join(directory, _generate_filename(wf_id, wf_name))
            op = "create"

        if ns.dry_run:
            print(f"  {op}: {os.path.basename(target_path)} ({wf_name})")
            if op == "create":
                created += 1
            else:
                updated += 1
            continue

        # Write file atomically
        try:
            content = json.dumps(wf, indent=2) + "\n"
            atomic_write(target_path, content)
            print(f"  {op}: {os.path.basename(target_path)} ({wf_name})")
            if op == "create":
                created += 1
            else:
                updated += 1
        except OSError as e:
            print(f"  error: {target_path}: {e}")
            errors += 1

    print(f"\nSummary: {created} created, {updated} updated, {skipped} skipped, {errors} errors")
    if errors > 0:
        raise SystemExit(1)
