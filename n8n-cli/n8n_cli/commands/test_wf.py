"""Test command — trigger a workflow via its webhook and check results."""

import json
import time
import urllib.error
import urllib.request
from argparse import Namespace
from typing import Any

from n8n_cli.client import Client
from n8n_cli.errors import CLIError
from n8n_cli.output import emit_json, emit_kv, enc


class WebhookTestError(CLIError):
    """Error during workflow test execution."""


def _find_webhook_node(workflow: dict[str, Any]) -> dict[str, Any]:
    """Find the first webhook node in a workflow.

    Prefers nodes named with '[CLI Test]' prefix, falls back to any webhook.
    """
    nodes = workflow.get("nodes", [])
    cli_test_node = None
    any_webhook = None

    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") != "n8n-nodes-base.webhook":
            continue
        name = node.get("name", "")
        if name.startswith("[CLI Test]"):
            cli_test_node = node
            break
        if any_webhook is None:
            any_webhook = node

    result = cli_test_node or any_webhook
    if result is None:
        wf_name = workflow.get("name", "")
        wf_id = workflow.get("id", "")
        raise WebhookTestError(f'No webhook node found in workflow "{wf_name}" ({wf_id})')
    return result


def _build_webhook_url(api_url: str, webhook_path: str) -> str:
    """Build the production webhook URL from the API URL and webhook path."""
    # Strip /api/v1 suffix to get the base n8n URL
    base = api_url.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    webhook_path = webhook_path.lstrip("/")
    return f"{base}/webhook/{webhook_path}"


def _call_webhook(
    url: str,
    method: str,
    data: Any,
    timeout: int,
) -> tuple[int, str]:
    """Send HTTP request to webhook, return (status, body)."""
    body_bytes = None
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if data is not None:
        body_bytes = json.dumps(data).encode()

    req = urllib.request.Request(url, data=body_bytes, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        return e.code, body_text
    except urllib.error.URLError as e:
        raise WebhookTestError(f"Webhook request failed: {e.reason}") from e


def _wait_for_execution(
    client: Client,
    workflow_id: str,
    timeout_s: int,
    poll_s: int = 1,
) -> dict[str, Any]:
    """Poll for the latest execution of a workflow to reach terminal status."""
    # Brief delay for n8n to create the execution record
    time.sleep(0.5)

    # Get latest execution
    result = client.get(f"/executions?workflowId={enc(workflow_id)}&limit=1&includeData=true")
    items = result.get("data", []) if isinstance(result, dict) else []
    if not items:
        raise WebhookTestError(f"No execution found for workflow {workflow_id}")

    execution: dict[str, Any] = items[0]
    exec_id = execution.get("id", "")
    terminal = {"success", "error", "crashed"}

    if execution.get("status", "") in terminal:
        return execution

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        resp = client.get(f"/executions/{enc(exec_id)}?includeData=true")
        if isinstance(resp, dict) and resp.get("status", "") in terminal:
            return resp

    raise WebhookTestError(f"Timeout waiting for execution {exec_id} to complete")


def cmd_test(client: Client, ns: Namespace) -> None:
    """Test a workflow by triggering its webhook."""
    workflow = client.get(f"/workflows/{enc(ns.id)}")
    if not isinstance(workflow, dict):
        raise WebhookTestError(f"Unexpected response for workflow {ns.id}")

    wf_name = workflow.get("name", "")
    wf_id = workflow.get("id", ns.id)

    # Find webhook
    webhook_node = _find_webhook_node(workflow)
    params = webhook_node.get("parameters", {})
    webhook_path = params.get("path", webhook_node.get("id", ""))
    http_method = params.get("httpMethod", "POST")

    webhook_url = _build_webhook_url(client.base_url, webhook_path)

    # Dry run: just show the URL
    if ns.dry_run:
        if ns.use_json:
            emit_json(
                {
                    "workflow": {"id": wf_id, "name": wf_name},
                    "webhookURL": webhook_url,
                    "httpMethod": http_method,
                    "dryRun": True,
                }
            )
        else:
            emit_kv(
                {
                    "Workflow": f"{wf_name} ({wf_id})",
                    "Webhook": webhook_node.get("name", ""),
                    "URL": webhook_url,
                    "Method": http_method,
                }
            )
            print("\n(dry-run — no request sent)")
        return

    # Auto-activate if requested
    if not workflow.get("active") and ns.activate:
        client.post(f"/workflows/{enc(wf_id)}/activate")
    elif not workflow.get("active"):
        raise WebhookTestError(
            f'Workflow "{wf_name}" ({wf_id}) is not active. Use --activate to auto-activate.'
        )

    # Parse data
    data: Any = {}
    if ns.data:
        try:
            data = json.loads(ns.data)
        except json.JSONDecodeError as e:
            raise WebhookTestError(f"Invalid JSON data: {e}") from None

    # Call webhook
    status_code, response_body = _call_webhook(webhook_url, http_method, data, ns.timeout)

    # Optionally wait for execution
    execution = None
    if ns.wait_execution:
        execution = _wait_for_execution(client, wf_id, ns.execution_timeout)

    # Output
    if ns.use_json:
        out: dict[str, Any] = {
            "workflow": {"id": wf_id, "name": wf_name},
            "webhookURL": webhook_url,
            "httpStatus": status_code,
            "success": 200 <= status_code < 300,
        }
        try:
            out["response"] = json.loads(response_body)
        except (json.JSONDecodeError, ValueError):
            out["response"] = response_body
        if execution:
            out["execution"] = {
                "id": execution.get("id", ""),
                "status": execution.get("status", ""),
            }
            out["success"] = out["success"] and execution.get("status") == "success"
        emit_json(out)
    else:
        print(f"Testing workflow: {wf_name} ({wf_id})")
        print(f"  Webhook: {webhook_node.get('name', '')}")
        print(f"  URL: {webhook_url}")
        print()
        print(f"  Status: {status_code}")
        if response_body:
            try:
                pretty = json.dumps(json.loads(response_body), indent=2)
                print(f"  Response:\n  {pretty}")
            except (json.JSONDecodeError, ValueError):
                display = response_body[:500] + "..." if len(response_body) > 500 else response_body
                print(f"  Response: {display}")

        if execution:
            print()
            exec_status = execution.get("status", "")
            print(f"Execution: {execution.get('id', '')}")
            print(f"  Status: {exec_status}")
            err_data = (
                execution.get("data", {}).get("resultData", {}).get("error")
                if isinstance(execution.get("data"), dict)
                else None
            )
            if isinstance(err_data, dict):
                print(f"  Error: {err_data.get('message', '')}")
                if err_data.get("node"):
                    print(f"  Failed node: {err_data['node']}")

        success = 200 <= status_code < 300
        if execution:
            success = success and execution.get("status") == "success"
        print()
        if success:
            print("✓ Test passed")
        else:
            print("✗ Test failed")
            raise WebhookTestError("Test failed")
