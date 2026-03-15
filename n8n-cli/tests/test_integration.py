"""Integration tests — exercise every CLI command against a fake n8n server.

Spins up a real HTTP server on localhost so the full code path is tested:
argv parsing → argparse → config → Client → urllib → HTTP → response handling → output.
"""

import json
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from n8n_cli.main import main

# ---------------------------------------------------------------------------
# Fake n8n API server
# ---------------------------------------------------------------------------

# Realistic payloads modelled on actual n8n v1 API responses.

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
            "/api/v1/workflows/wf-1": WORKFLOW_1,
            "/api/v1/executions/exec-100": EXECUTION_1,
            "/api/v1/executions": {"data": [EXECUTION_1]},
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

        routes: dict[str, Any] = {
            "/api/v1/credentials": {**CREDENTIAL_1, "id": "43", "name": "New Cred"},
            "/api/v1/credentials/42/test": {"status": "ok", "message": "Connection successful"},
            "/api/v1/workflows/wf-1/activate": {**WORKFLOW_1, "active": True},
            "/api/v1/workflows/wf-1/deactivate": {**WORKFLOW_1, "active": False},
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

        if p in (
            "/api/v1/credentials/42",
            "/api/v1/data-tables/dt-1",
            "/api/v1/data-tables/dt-1/rows/delete",
        ):
            self._send(200, {})
        else:
            self._send(404, {"message": f"Not found: {p}"})


@pytest.fixture(scope="module")
def server() -> Generator[tuple[str, int]]:
    """Start a fake n8n server for the test module. Returns (host, port)."""
    httpd = HTTPServer(("127.0.0.1", 0), FakeN8NHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield "127.0.0.1", port
    httpd.shutdown()


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Credential commands
# ---------------------------------------------------------------------------


class TestCredential:
    def test_list_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["credential", "list"], capsys)
        assert "42" in out
        assert "My Slack Token" in out
        assert "slackApi" in out

    def test_list_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "credential", "list"], capsys)
        data = json.loads(out)
        assert data["data"][0]["id"] == "42"

    def test_get_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["credential", "get", "42"], capsys)
        assert "My Slack Token" in out
        assert "slackApi" in out

    def test_get_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "credential", "get", "42"], capsys)
        data = json.loads(out)
        assert data["id"] == "42"

    def test_create(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "cred.json"
        f.write_text(json.dumps({"name": "New", "type": "slackApi", "data": {"accessToken": "x"}}))
        out = run_ok(server, ["credential", "create", str(f)], capsys)
        assert "Created" in out
        assert "New Cred" in out

    def test_update(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "cred.json"
        f.write_text(json.dumps({"name": "Updated Cred"}))
        out = run_ok(server, ["credential", "update", "42", str(f)], capsys)
        assert "Updated" in out

    def test_delete(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["credential", "delete", "42"], capsys)
        assert "Deleted" in out
        assert "42" in out

    def test_test(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["credential", "test", "42"], capsys)
        assert "ok" in out
        assert "Connection successful" in out

    def test_schema(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["credential", "schema", "slackApi"], capsys)
        data = json.loads(out)
        assert "accessToken" in data["properties"]


# ---------------------------------------------------------------------------
# Workflow commands
# ---------------------------------------------------------------------------


class TestWorkflow:
    def test_get_always_json(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """workflow get always outputs full JSON for round-trip editing."""
        out = run_ok(server, ["workflow", "get", "wf-1"], capsys)
        data = json.loads(out)
        assert data["id"] == "wf-1"
        assert data["name"] == "Daily Report"
        assert len(data["nodes"]) == 2

    def test_update_strips_metadata(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """workflow update strips id/createdAt/updatedAt/tags/shared/pinData."""
        wf = {
            **WORKFLOW_1,
            "pinData": {"Start": [{}]},
            "shared": [{"userId": "1"}],
        }
        f = tmp_path / "wf.json"
        f.write_text(json.dumps(wf))
        # The fake server asserts these keys are NOT present
        out = run_ok(server, ["workflow", "update", "wf-1", str(f)], capsys)
        assert "Daily Report" in out

    def test_update_json(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "wf.json"
        f.write_text(json.dumps(WORKFLOW_1))
        out = run_ok(server, ["-j", "workflow", "update", "wf-1", str(f)], capsys)
        data = json.loads(out)
        assert data["id"] == "wf-1"

    def test_activate(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["workflow", "activate", "wf-1"], capsys)
        assert "Activated" in out
        assert "Daily Report" in out

    def test_deactivate(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["workflow", "deactivate", "wf-1"], capsys)
        assert "Deactivated" in out


# ---------------------------------------------------------------------------
# Execution commands
# ---------------------------------------------------------------------------


class TestExecution:
    def test_get_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["execution", "get", "exec-100"], capsys)
        assert "exec-100" in out
        assert "success" in out
        assert "Fetch" in out
        assert "150ms" in out
        assert "✓" in out

    def test_get_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "execution", "get", "exec-100"], capsys)
        data = json.loads(out)
        assert data["id"] == "exec-100"
        assert "runData" in data["data"]["resultData"]

    def test_list_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["execution", "list"], capsys)
        assert "exec-100" in out
        assert "wf-1" in out

    def test_list_with_filters(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = run_ok(
            server,
            ["execution", "list", "--workflow", "wf-1", "--status", "success", "--limit", "5"],
            capsys,
        )
        assert "exec-100" in out


# ---------------------------------------------------------------------------
# Data table commands
# ---------------------------------------------------------------------------


class TestDatatable:
    def test_list_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["datatable", "list"], capsys)
        assert "dt-1" in out
        assert "Contacts" in out

    def test_list_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "datatable", "list"], capsys)
        data = json.loads(out)
        assert data["data"][0]["name"] == "Contacts"

    def test_get_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["datatable", "get", "dt-1"], capsys)
        assert "Contacts" in out
        assert "name:string" in out
        assert "email:string" in out

    def test_create(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "dt.json"
        f.write_text(
            json.dumps({"name": "New Table", "columns": [{"name": "x", "type": "string"}]})
        )
        out = run_ok(server, ["datatable", "create", str(f)], capsys)
        assert "Created" in out
        assert "New Table" in out

    def test_update(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["datatable", "update", "dt-1", "Renamed"], capsys)
        assert "Renamed" in out

    def test_delete(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["datatable", "delete", "dt-1"], capsys)
        assert "Deleted" in out
        assert "dt-1" in out

    def test_rows_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["datatable", "rows", "dt-1"], capsys)
        assert "Alice" in out
        assert "Bob" in out

    def test_rows_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "datatable", "rows", "dt-1"], capsys)
        data = json.loads(out)
        assert len(data["data"]) == 2

    def test_insert(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "rows.json"
        f.write_text(json.dumps([{"name": "Charlie", "email": "c@x.com"}]))
        out = run_ok(server, ["datatable", "insert", "dt-1", str(f)], capsys)
        data = json.loads(out)
        assert data["created"] == 2

    def test_update_rows(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "upd.json"
        f.write_text(json.dumps({"filter": {}, "data": {"name": "Updated"}}))
        out = run_ok(server, ["datatable", "update-rows", "dt-1", str(f)], capsys)
        data = json.loads(out)
        assert data["updated"] == 1

    def test_upsert(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "ups.json"
        f.write_text(json.dumps({"filter": {}, "data": {"name": "Upserted"}}))
        out = run_ok(server, ["datatable", "upsert", "dt-1", str(f)], capsys)
        data = json.loads(out)
        assert data["updated"] == 1

    def test_delete_rows(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(
            server,
            ["datatable", "delete-rows", "dt-1", "--filter", '{"id": "row-1"}'],
            capsys,
        )
        data = json.loads(out)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Raw command
# ---------------------------------------------------------------------------


class TestRaw:
    def test_get(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["raw", "GET", "/custom/endpoint"], capsys)
        data = json.loads(out)
        assert data["ok"] is True

    def test_post(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "body.json"
        f.write_text(json.dumps({"key": "val"}))
        out = run_ok(
            server,
            ["raw", "POST", "/credentials", str(f)],
            capsys,
        )
        data = json.loads(out)
        assert data["id"] == "43"

    def test_delete(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["raw", "DELETE", "/credentials/42"], capsys)
        data = json.loads(out)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_credentials(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing API URL/key produces a ConfigError, not a traceback."""
        env = {"N8N_API_URL": "", "N8N_API_KEY": ""}
        with patch.dict("os.environ", env, clear=False):
            with patch("sys.argv", ["n8n-cli", "credential", "list"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "N8N_API_URL" in err

    def test_api_404(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        """Requesting a non-existent resource shows a friendly error."""
        err = run_fail(server, ["credential", "get", "nonexistent"], capsys)
        assert "Not Found" in err

    def test_bad_json_file(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Invalid JSON input shows InputError, not a raw traceback."""
        f = tmp_path / "bad.json"
        f.write_text("not json{{{")
        err = run_fail(server, ["credential", "create", str(f)], capsys)
        assert "Invalid JSON" in err

    def test_missing_file(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-existent file shows InputError."""
        err = run_fail(server, ["credential", "create", "/no/such/file.json"], capsys)
        assert "File not found" in err

    def test_workflow_update_non_object(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """workflow update rejects non-object JSON."""
        f = tmp_path / "arr.json"
        f.write_text("[1, 2, 3]")
        err = run_fail(server, ["workflow", "update", "wf-1", str(f)], capsys)
        assert "object" in err.lower()

    def test_datatable_delete_rows_bad_filter(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """delete-rows with invalid filter JSON shows InputError."""
        err = run_fail(
            server,
            ["datatable", "delete-rows", "dt-1", "--filter", "not-json"],
            capsys,
        )
        assert "Invalid filter JSON" in err

    def test_raw_unsupported_method(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        err = run_fail(server, ["raw", "TRACE", "/foo"], capsys)
        assert "Unsupported HTTP method" in err

    def test_unknown_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unknown top-level command exits with code 2 (argparse error)."""
        with patch.dict("os.environ", {"N8N_API_URL": "x", "N8N_API_KEY": "x"}):
            with patch("sys.argv", ["n8n-cli", "bogus"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------


class TestHelp:
    def test_top_level_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["n8n-cli", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "credential" in out
        assert "workflow" in out
        assert "datatable" in out
        assert "raw" in out

    def test_subcommand_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["n8n-cli", "credential", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "list" in out
        assert "get" in out
        assert "schema" in out
