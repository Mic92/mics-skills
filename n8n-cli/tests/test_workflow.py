"""Workflow command tests."""

import json
from pathlib import Path

import pytest

from tests.conftest import WORKFLOW_1, run_fail, run_ok


class TestWorkflow:
    def test_list_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["workflow", "list"], capsys)
        assert "wf-1" in out
        assert "Daily Report" in out
        assert "production" in out

    def test_list_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "workflow", "list"], capsys)
        data = json.loads(out)
        assert data["data"][0]["id"] == "wf-1"

    def test_list_active_filter(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = run_ok(server, ["workflow", "list", "--active"], capsys)
        assert "wf-1" in out

    def test_list_with_tags(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = run_ok(server, ["workflow", "list", "--tags", "production"], capsys)
        assert "wf-1" in out

    def test_get_always_json(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """workflow get always outputs full JSON for round-trip editing."""
        out = run_ok(server, ["workflow", "get", "wf-1"], capsys)
        data = json.loads(out)
        assert data["id"] == "wf-1"
        assert data["name"] == "Daily Report"
        assert len(data["nodes"]) == 2

    def test_create(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "wf.json"
        f.write_text(json.dumps({"name": "New Workflow", "nodes": [], "connections": {}}))
        out = run_ok(server, ["workflow", "create", str(f)], capsys)
        assert "Created" in out
        assert "New Workflow" in out

    def test_create_json(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "wf.json"
        f.write_text(json.dumps({"name": "New Workflow", "nodes": [], "connections": {}}))
        out = run_ok(server, ["-j", "workflow", "create", str(f)], capsys)
        data = json.loads(out)
        assert data["id"] == "wf-2"

    def test_create_rejects_non_object(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        f = tmp_path / "arr.json"
        f.write_text("[1, 2, 3]")
        err = run_fail(server, ["workflow", "create", str(f)], capsys)
        assert "object" in err.lower()

    def test_update_strips_metadata(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """workflow update strips all read-only fields from round-trip JSON."""
        wf = {
            **WORKFLOW_1,
            "pinData": {"Start": [{}]},
            "staticData": {"lastId": 5},
            "meta": {"instanceId": "abc123"},
            "shared": [{"userId": "1"}],
            "isArchived": False,
            "homeProject": {"id": "proj-1"},
            "sharedWithProjects": [],
            "scopes": ["workflow:read"],
            "usedCredentials": [{"id": "42"}],
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

    def test_update_rejects_non_object(
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

    def test_delete(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["workflow", "delete", "wf-1"], capsys)
        assert "Deleted" in out
        assert "wf-1" in out

    def test_delete_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "workflow", "delete", "wf-1"], capsys)
        data = json.loads(out)
        assert data["id"] == "wf-1"

    def test_activate(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["workflow", "activate", "wf-1"], capsys)
        assert "Activated" in out
        assert "Daily Report" in out

    def test_deactivate(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["workflow", "deactivate", "wf-1"], capsys)
        assert "Deactivated" in out
