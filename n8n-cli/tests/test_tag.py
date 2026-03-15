"""Tag command tests."""

import json

import pytest

from tests.conftest import run_ok


class TestTag:
    def test_list_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["tag", "list"], capsys)
        assert "tag-1" in out
        assert "production" in out

    def test_list_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "tag", "list"], capsys)
        data = json.loads(out)
        assert data["data"][0]["name"] == "production"

    def test_get_text(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["tag", "get", "tag-1"], capsys)
        assert "production" in out
        assert "tag-1" in out

    def test_get_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "tag", "get", "tag-1"], capsys)
        data = json.loads(out)
        assert data["id"] == "tag-1"

    def test_create(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["tag", "create", "staging"], capsys)
        assert "Created" in out
        assert "staging" in out

    def test_create_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "tag", "create", "staging"], capsys)
        data = json.loads(out)
        assert data["name"] == "staging"

    def test_update(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["tag", "update", "tag-1", "renamed-tag"], capsys)
        assert "Updated" in out
        assert "renamed-tag" in out

    def test_delete(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["tag", "delete", "tag-1"], capsys)
        assert "Deleted" in out
        assert "tag-1" in out

    def test_delete_json(self, server: tuple[str, int], capsys: pytest.CaptureFixture[str]) -> None:
        out = run_ok(server, ["-j", "tag", "delete", "tag-1"], capsys)
        data = json.loads(out)
        assert data["deleted"] is True
