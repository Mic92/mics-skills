"""Execution management commands."""

import urllib.parse
from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.output import emit, emit_json, emit_kv, emit_table, enc, ts


def _text_summary(exc: dict[str, Any]) -> None:
    """Print a compact execution summary with error/node details."""
    emit_kv(
        {
            "ID": str(exc.get("id", "")),
            "Workflow": str(exc.get("workflowId", "")),
            "Status": str(exc.get("status", "")),
            "Mode": str(exc.get("mode", "")),
            "Started": ts(exc.get("startedAt")),
            "Stopped": ts(exc.get("stoppedAt")),
        }
    )

    data = exc.get("data")
    if not isinstance(data, dict):
        return
    result_data = data.get("resultData")
    if not isinstance(result_data, dict):
        return

    error = result_data.get("error")
    if isinstance(error, dict):
        print()
        kv: dict[str, str] = {
            "Error node": str(error.get("node", "-")),
            "Error": str(error.get("message", "")),
        }
        desc = error.get("description")
        if desc:
            kv["Details"] = str(desc)
        emit_kv(kv)

    last = result_data.get("lastNodeExecuted")
    if last:
        print(f"\nLast node: {last}")

    run_data = result_data.get("runData")
    if isinstance(run_data, dict) and run_data:
        print()
        rows: list[list[str]] = []
        for node_name, runs in run_data.items():
            if not isinstance(runs, list):
                continue
            for run in runs:
                if not isinstance(run, dict):
                    continue
                ms = str(run.get("executionTime", 0))
                err = run.get("error")
                if isinstance(err, dict):
                    status = f"✗ {err.get('message', 'error')}"
                else:
                    status = "✓"
                rows.append([node_name, f"{ms}ms", status])
        emit_table(["NODE", "TIME", "STATUS"], rows)


def cmd_execution_get(client: Client, ns: Namespace) -> None:
    """Get execution by ID with full runData."""
    result = client.get(f"/executions/{enc(ns.id)}?includeData=true")
    emit(result, use_json=ns.use_json, text_fn=_text_summary)


def cmd_execution_list(client: Client, ns: Namespace) -> None:
    """List executions with optional filters."""
    params: dict[str, str] = {"limit": str(ns.limit)}
    if ns.workflow:
        params["workflowId"] = ns.workflow
    if ns.status:
        params["status"] = ns.status

    qs = urllib.parse.urlencode(params)
    result = client.get(f"/executions?{qs}")

    def text(data: dict[str, object]) -> None:
        items = data.get("data", data)
        if not isinstance(items, list):
            emit_json(data)
            return
        emit_table(
            ["ID", "WORKFLOW", "STATUS", "MODE", "STARTED", "STOPPED"],
            [
                [
                    str(e.get("id", "")),
                    str(e.get("workflowId", "")),
                    str(e.get("status", "")),
                    str(e.get("mode", "")),
                    ts(e.get("startedAt")),
                    ts(e.get("stoppedAt")),
                ]
                for e in items
                if isinstance(e, dict)
            ],
        )

    emit(result, use_json=ns.use_json, text_fn=text)
