"""Apply command — push local workflow JSON files to n8n server."""

import json
import os
from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.errors import APIError, CLIError
from n8n_cli.output import atomic_write, enc
from n8n_cli.strip import WORKFLOW_READONLY, strip_readonly


class ApplyError(CLIError):
    """Error during workflow apply."""


def _scan_workflows(directory: str, ids: list[str] | None) -> list[tuple[str, dict[str, Any]]]:
    """Scan directory for workflow JSON files. Returns list of (path, data).

    Walks recursively, skipping _subfiles directories.
    """
    if not os.path.isdir(directory):
        raise ApplyError(f"Directory not found: {directory}")

    results: list[tuple[str, dict[str, Any]]] = []
    seen_ids: dict[str, str] = {}

    for root, dirs, files in os.walk(directory):
        # Skip _subfiles directories
        dirs[:] = [d for d in dirs if d != "_subfiles"]
        for fname in sorted(files):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  error: {path}: invalid JSON: {e}")
                continue
            except OSError as e:
                print(f"  error: {path}: {e}")
                continue

            if not isinstance(data, dict):
                print(f"  error: {path}: not a JSON object")
                continue

            # Validate minimum fields
            if not data.get("name"):
                print(f"  error: {path}: missing 'name' field")
                continue
            if data.get("nodes") is None:
                print(f"  error: {path}: missing 'nodes' field")
                continue
            if data.get("connections") is None:
                print(f"  error: {path}: missing 'connections' field")
                continue

            wf_id = data.get("id")

            # Filter by IDs if specified
            if ids:
                if not wf_id or wf_id not in ids:
                    continue

            # Check for duplicate IDs
            if wf_id and wf_id in seen_ids:
                raise ApplyError(
                    f"Duplicate workflow ID {wf_id}:\n  - {seen_ids[wf_id]}\n  - {path}"
                )
            if wf_id:
                seen_ids[wf_id] = path

            results.append((path, data))

    return results


def _strip_for_create(data: dict[str, Any]) -> dict[str, Any]:
    """Strip fields not accepted by the create endpoint."""
    body: dict[str, Any] = {
        "name": data["name"],
        "nodes": data["nodes"],
        "connections": data["connections"],
    }
    if data.get("settings"):
        body["settings"] = data["settings"]
    if data.get("staticData"):
        body["staticData"] = data["staticData"]
    return body


def _strip_for_update(data: dict[str, Any]) -> dict[str, Any]:
    """Strip read-only fields not accepted by the update endpoint."""
    return strip_readonly(data, WORKFLOW_READONLY)


def _update_local_file(path: str, created: dict[str, Any]) -> None:
    """Update local JSON file with server-assigned id and timestamps."""
    try:
        with open(path) as f:
            local = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(local, dict):
        return

    local["id"] = created.get("id")
    if created.get("updatedAt"):
        local["updatedAt"] = created["updatedAt"]
    if created.get("createdAt"):
        local["createdAt"] = created["createdAt"]

    try:
        atomic_write(path, json.dumps(local, indent=2) + "\n")
    except OSError:
        pass  # Best-effort; the server operation already succeeded


def _workflows_differ(local: dict[str, Any], remote: dict[str, Any]) -> bool:
    """Check if local and remote workflows differ in meaningful fields."""

    def _normalize(v: Any) -> Any:
        """Normalize for comparison: strip None, sort keys."""
        if v is None:
            return None
        s = json.dumps(v, sort_keys=True, separators=(",", ":"))
        return s

    for field in ("name", "nodes", "connections", "settings"):
        if _normalize(local.get(field)) != _normalize(remote.get(field)):
            return True
    # Compare active state
    if local.get("active") != remote.get("active"):
        return True
    return False


def cmd_apply(client: Client, ns: Namespace) -> None:
    """Apply local workflow JSON files to n8n server."""
    directory = ns.dir

    # Parse IDs filter
    ids: list[str] | None = None
    if ns.ids:
        ids = [s.strip() for s in ns.ids.split(",") if s.strip()]

    files = _scan_workflows(directory, ids)
    if not files:
        print("No workflow files found.")
        return

    created = 0
    updated = 0
    skipped = 0
    errors = 0
    conflicts = 0

    for path, data in files:
        wf_name = data.get("name", "")
        wf_id = data.get("id")
        basename = os.path.basename(path)

        if not wf_id:
            # No ID = create
            if ns.dry_run:
                print(f"  create: {basename} ({wf_name})")
                created += 1
                continue

            try:
                body = _strip_for_create(data)
                result = client.post("/workflows", body)
                _update_local_file(path, result)
                print(f"  create: {basename} → {result.get('id', '')} ({wf_name})")
                created += 1
            except (APIError, OSError) as e:
                print(f"  error: {basename}: {e}")
                errors += 1
            continue

        # Has ID — fetch remote to compare
        try:
            remote = client.get(f"/workflows/{enc(wf_id)}")
        except APIError as e:
            if e.status == 404:
                # Not on server — create with ID preserved
                if ns.dry_run:
                    print(f"  create: {basename} ({wf_name}) [id: {wf_id}]")
                    created += 1
                    continue

                try:
                    body = _strip_for_create(data)
                    result = client.post("/workflows", body)
                    _update_local_file(path, result)
                    print(f"  create: {basename} → {result.get('id', '')} ({wf_name})")
                    created += 1
                except (APIError, OSError) as e2:
                    print(f"  error: {basename}: {e2}")
                    errors += 1
                continue
            print(f"  error: {basename}: {e}")
            errors += 1
            continue

        if not isinstance(remote, dict):
            print(f"  error: {basename}: unexpected remote response")
            errors += 1
            continue

        # Compare
        if not _workflows_differ(data, remote):
            print(f"  skip: {basename} (no changes)")
            skipped += 1
            continue

        # Conflict detection: remote newer than local
        local_updated = data.get("updatedAt")
        remote_updated = remote.get("updatedAt")
        if local_updated and remote_updated and remote_updated > local_updated:
            if not ns.force:
                print(
                    f"  conflict: {basename} (remote is newer: {remote_updated} > {local_updated})"
                )
                conflicts += 1
                continue

        # Update
        if ns.dry_run:
            print(f"  update: {basename} ({wf_name})")
            updated += 1
            continue

        try:
            body = _strip_for_update(data)
            result = client.put(f"/workflows/{enc(wf_id)}", body)
            _update_local_file(path, result)
            print(f"  update: {basename} ({wf_name})")
            updated += 1
        except (APIError, OSError) as e:
            print(f"  error: {basename}: {e}")
            errors += 1

    prefix = "(dry-run) " if ns.dry_run else ""
    parts = [
        f"{created} created",
        f"{updated} updated",
        f"{skipped} skipped",
    ]
    if conflicts:
        parts.append(f"{conflicts} conflicts")
    if errors:
        parts.append(f"{errors} errors")
    print(f"\n{prefix}Summary: {', '.join(parts)}")

    if errors > 0:
        raise SystemExit(1)
    if conflicts > 0:
        raise SystemExit(2)
