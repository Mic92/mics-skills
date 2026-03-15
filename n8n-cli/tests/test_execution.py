"""Execution command tests."""

import json

import pytest

from tests.conftest import run_ok


class TestExecution:
    def test_get_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        """Without --show-data, shows summary but not node run table."""
        out = run_ok(server, ["execution", "get", "exec-100"], capsys)
        assert "exec-100" in out
        assert "success" in out

    def test_get_show_data(
        self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With --show-data, shows full node execution table."""
        out = run_ok(server, ["execution", "get", "exec-100", "--show-data"], capsys)
        assert "exec-100" in out
        assert "success" in out
        assert "Fetch" in out
        assert "150ms" in out
        assert "✓" in out

    def test_get_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "execution", "get", "exec-100", "--show-data"], capsys)
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

    def test_delete(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["execution", "delete", "exec-100"], capsys)
        assert "Deleted" in out
        assert "exec-100" in out

    def test_delete_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "execution", "delete", "exec-100"], capsys)
        data = json.loads(out)
        assert data["id"] == "exec-100"

    def test_retry(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["execution", "retry", "exec-100"], capsys)
        assert "exec-101" in out
        assert "retry started" in out.lower()

    def test_retry_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "execution", "retry", "exec-100"], capsys)
        data = json.loads(out)
        assert data["id"] == "exec-101"

    def test_stop(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["execution", "stop", "exec-100"], capsys)
        assert "stopped" in out.lower()

    def test_stop_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "execution", "stop", "exec-100"], capsys)
        data = json.loads(out)
        assert data["status"] == "canceled"
