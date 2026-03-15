"""Shared fixtures — fake n8n API server and CLI test helpers."""

import json
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from unittest.mock import patch

import pytest

from n8n_cli.main import main

# ---------------------------------------------------------------------------
# Realistic payloads modelled on actual n8n v1 API responses
# ---------------------------------------------------------------------------

CREDENTIAL_1 = {
    "id": "42",
    "name": "My Slack Token",
    "type": "slackApi",
    "createdAt": "2025-01-10T08:00:00.000Z",
    "updatedAt": "2025-03-01T12:30:00.000Z",
}

CREDENTIAL_SCHEMA = {
    "additionalProperties": False,
    "properties": {
        "accessToken": {"type": "string"},
    },
    "required": ["accessToken"],
}

WORKFLOW_1 = {
    "id": "wf-1",
    "name": "Daily Report",
    "active": True,
    "nodes": [
        {"type": "n8n-nodes-base.start", "name": "Start"},
        {"type": "n8n-nodes-base.httpRequest", "name": "Fetch"},
    ],
    "connections": {},
    "tags": [{"name": "production"}],
    "createdAt": "2025-02-01T09:00:00.000Z",
    "updatedAt": "2025-03-10T16:45:00.000Z",
}

EXECUTION_1 = {
    "id": "exec-100",
    "workflowId": "wf-1",
    "status": "success",
    "mode": "trigger",
    "startedAt": "2025-03-14T10:00:00.000Z",
    "stoppedAt": "2025-03-14T10:00:05.000Z",
    "data": {
        "resultData": {
            "lastNodeExecuted": "Fetch",
            "runData": {
                "Start": [{"executionTime": 2}],
                "Fetch": [{"executionTime": 150}],
            },
        },
    },
}

DATATABLE_1 = {
    "id": "dt-1",
    "name": "Contacts",
    "columns": [
        {"name": "name", "type": "string"},
        {"name": "email", "type": "string"},
    ],
    "createdAt": "2025-03-01T10:00:00.000Z",
    "updatedAt": "2025-03-14T08:00:00.000Z",
}

ROW_1 = {"id": "row-1", "name": "Alice", "email": "alice@example.com"}
ROW_2 = {"id": "row-2", "name": "Bob", "email": "bob@example.com"}

TAG_1 = {
    "id": "tag-1",
    "name": "production",
    "createdAt": "2025-01-05T10:00:00.000Z",
    "updatedAt": "2025-02-20T14:00:00.000Z",
}

WORKFLOW_WEBHOOK = {
    "id": "wf-2",
    "name": "Webhook Test",
    "active": True,
    "nodes": [
        {
            "id": "node-1",
            "name": "[CLI Test] Entry",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1,
            "position": [0, 0],
            "parameters": {"httpMethod": "POST", "path": "test-hook"},
            "webhookId": "test-hook",
        },
    ],
    "connections": {},
    "tags": [],
    "createdAt": "2025-02-01T09:00:00.000Z",
    "updatedAt": "2025-03-10T16:45:00.000Z",
}

EXECUTION_RETRY_RESULT = {
    "id": "exec-101",
    "workflowId": "wf-1",
    "status": "running",
    "mode": "retry",
    "startedAt": "2025-03-14T11:00:00.000Z",
}

EXECUTION_STOPPED = {
    "id": "exec-100",
    "workflowId": "wf-1",
    "status": "canceled",
    "mode": "trigger",
    "startedAt": "2025-03-14T10:00:00.000Z",
    "stoppedAt": "2025-03-14T10:00:02.000Z",
}


# ---------------------------------------------------------------------------
# Fake n8n API server
# ---------------------------------------------------------------------------


class FakeN8NHandler(BaseHTTPRequestHandler):
    """Route requests to canned responses based on method + path."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # silence server logs during tests

    def _send(self, code: int, body: Any) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    # -- routing -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        p = self.path.split("?")[0]  # strip query string for matching

        routes: dict[str, Any] = {
            "/api/v1/credentials": {"data": [CREDENTIAL_1]},
            "/api/v1/credentials/42": CREDENTIAL_1,
            "/api/v1/credentials/schema/slackApi": CREDENTIAL_SCHEMA,
            "/api/v1/workflows": {"data": [WORKFLOW_1, WORKFLOW_WEBHOOK]},
            "/api/v1/workflows/wf-1": WORKFLOW_1,
            "/api/v1/workflows/wf-2": WORKFLOW_WEBHOOK,
            "/api/v1/executions/exec-100": EXECUTION_1,
            "/api/v1/executions": {"data": [EXECUTION_1]},
            "/api/v1/tags": {"data": [TAG_1]},
            "/api/v1/tags/tag-1": TAG_1,
            "/api/v1/data-tables": {"data": [DATATABLE_1]},
            "/api/v1/data-tables/dt-1": DATATABLE_1,
            "/api/v1/data-tables/dt-1/rows": {"data": [ROW_1, ROW_2]},
            # raw escape hatch
            "/api/v1/custom/endpoint": {"ok": True},
        }
        body = routes.get(p)
        if body is not None:
            self._send(200, body)
        else:
            self._send(404, {"message": f"Not found: {p}"})

    def do_POST(self) -> None:  # noqa: N802
        self._read_body()
        p = self.path.split("?")[0]

        # Webhook endpoint (outside /api/v1)
        if p == "/webhook/test-hook":
            self._send(200, {"success": True, "received": True})
            return

        routes: dict[str, Any] = {
            "/api/v1/credentials": {**CREDENTIAL_1, "id": "43", "name": "New Cred"},
            "/api/v1/credentials/42/test": {"status": "ok", "message": "Connection successful"},
            "/api/v1/workflows": {**WORKFLOW_1, "id": "wf-2", "name": "New Workflow"},
            "/api/v1/workflows/wf-1/activate": {**WORKFLOW_1, "active": True},
            "/api/v1/workflows/wf-1/deactivate": {**WORKFLOW_1, "active": False},
            "/api/v1/workflows/wf-2/activate": {**WORKFLOW_WEBHOOK, "active": True},
            "/api/v1/executions/exec-100/retry": EXECUTION_RETRY_RESULT,
            "/api/v1/executions/exec-100/stop": EXECUTION_STOPPED,
            "/api/v1/tags": {**TAG_1, "id": "tag-2", "name": "staging"},
            "/api/v1/data-tables": {**DATATABLE_1, "id": "dt-2", "name": "New Table"},
            "/api/v1/data-tables/dt-1/rows": {"created": 2},
            "/api/v1/data-tables/dt-1/rows/upsert": {"updated": 1},
        }
        body = routes.get(p)
        if body is not None:
            self._send(200, body)
        else:
            self._send(404, {"message": f"Not found: {p}"})

    def do_PUT(self) -> None:  # noqa: N802
        raw = self._read_body()
        p = self.path.split("?")[0]

        if p == "/api/v1/workflows/wf-1":
            sent = json.loads(raw)
            # Verify round-trip stripping: these keys must NOT be in the body
            for forbidden in ("id", "createdAt", "updatedAt", "tags", "shared", "pinData"):
                assert forbidden not in sent, f"workflow update should strip '{forbidden}'"
            self._send(200, {**WORKFLOW_1, "name": sent.get("name", WORKFLOW_1["name"])})
        elif p == "/api/v1/tags/tag-1":
            sent = json.loads(raw)
            self._send(200, {**TAG_1, "name": sent.get("name", TAG_1["name"])})
        else:
            self._send(404, {"message": f"Not found: {p}"})

    def do_PATCH(self) -> None:  # noqa: N802
        self._read_body()
        p = self.path.split("?")[0]

        routes: dict[str, Any] = {
            "/api/v1/credentials/42": {**CREDENTIAL_1, "name": "Updated Cred"},
            "/api/v1/data-tables/dt-1": {**DATATABLE_1, "name": "Renamed"},
            "/api/v1/data-tables/dt-1/rows/update": {"updated": 1},
        }
        body = routes.get(p)
        if body is not None:
            self._send(200, body)
        else:
            self._send(404, {"message": f"Not found: {p}"})

    def do_DELETE(self) -> None:  # noqa: N802
        p = self.path.split("?")[0]

        delete_routes: dict[str, Any] = {
            "/api/v1/credentials/42": {},
            "/api/v1/workflows/wf-1": WORKFLOW_1,
            "/api/v1/executions/exec-100": {
                "id": "exec-100",
                "workflowId": "wf-1",
                "status": "success",
            },
            "/api/v1/tags/tag-1": {},
            "/api/v1/data-tables/dt-1": {},
            "/api/v1/data-tables/dt-1/rows/delete": {},
        }
        body = delete_routes.get(p)
        if body is not None:
            self._send(200, body)
        else:
            self._send(404, {"message": f"Not found: {p}"})


@pytest.fixture(scope="session")
def server() -> Generator[tuple[str, int]]:
    """Start a fake n8n server for the test session. Returns (host, port)."""
    httpd = HTTPServer(("127.0.0.1", 0), FakeN8NHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield "127.0.0.1", port
    httpd.shutdown()


# ---------------------------------------------------------------------------
# CLI test helpers
# ---------------------------------------------------------------------------


def run_ok(
    server: tuple[str, int],
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Run a CLI command that should succeed, return stdout."""
    host, port = server
    env = {
        "N8N_API_URL": f"http://{host}:{port}",
        "N8N_API_KEY": "test-key-1234",
    }
    with patch.dict("os.environ", env, clear=False):
        with patch("sys.argv", ["n8n-cli", *argv]):
            try:
                main()
            except SystemExit as e:
                assert e.code in (None, 0), f"Expected success but got exit {e.code}"
    out: str = capsys.readouterr().out
    return out


def run_fail(
    server: tuple[str, int],
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Run a CLI command that should fail, return stderr."""
    host, port = server
    env = {
        "N8N_API_URL": f"http://{host}:{port}",
        "N8N_API_KEY": "test-key-1234",
    }
    with patch.dict("os.environ", env, clear=False):
        with patch("sys.argv", ["n8n-cli", *argv]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0
    err: str = capsys.readouterr().err
    return err
