"""Credential command tests."""

import json
from pathlib import Path

import pytest

from tests.conftest import CREDENTIAL_1, run_fail, run_ok


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

    def test_update_strips_readonly(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """credential update strips read-only fields from round-trip JSON."""
        cred = {
            **CREDENTIAL_1,
            "name": "Updated Cred",
            "data": {"accessToken": "new-token"},
            "isManaged": False,
            "ownedBy": {"id": "user-1"},
            "homeProject": {"id": "proj-1"},
            "sharedWithProjects": [],
            "scopes": ["credential:read"],
        }
        f = tmp_path / "cred.json"
        f.write_text(json.dumps(cred))
        # The fake server asserts these read-only keys are NOT present
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

    def test_api_404(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        """Requesting a non-existent resource shows a friendly error."""
        err = run_fail(server, ["credential", "get", "nonexistent"], capsys)
        assert "Not Found" in err
