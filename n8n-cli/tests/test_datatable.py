"""Data table command tests."""

import json
from pathlib import Path

import pytest

from tests.conftest import run_fail, run_ok


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

    def test_delete_rows_bad_filter(
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
