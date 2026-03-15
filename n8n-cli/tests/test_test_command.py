"""Test (webhook trigger) command tests."""

import json

import pytest

from tests.conftest import run_fail, run_ok


class TestTestCommand:
    def test_dry_run(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        """test --dry-run shows webhook URL without calling it."""
        out = run_ok(server, ["test", "wf-2", "--dry-run"], capsys)
        assert "webhook/test-hook" in out
        assert "[CLI Test] Entry" in out

    def test_dry_run_json(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = run_ok(server, ["-j", "test", "wf-2", "--dry-run"], capsys)
        data = json.loads(out)
        assert "webhook/test-hook" in data["webhookURL"]
        assert data["dryRun"] is True

    def test_execute_webhook(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """test sends request to webhook and reports result."""
        out = run_ok(server, ["test", "wf-2", "-d", '{"key": "val"}'], capsys)
        assert "200" in out
        assert "Test passed" in out

    def test_execute_json(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = run_ok(server, ["-j", "test", "wf-2", "-d", "{}"], capsys)
        data = json.loads(out)
        assert data["httpStatus"] == 200
        assert data["success"] is True

    def test_no_webhook_node(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """test against workflow without webhook shows friendly error."""
        err = run_fail(server, ["test", "wf-1"], capsys)
        assert "No webhook node" in err
