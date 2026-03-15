"""Import command tests."""

import json
from pathlib import Path

import pytest

from tests.conftest import run_ok


class TestImportCommand:
    def test_dry_run(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """import --dry-run shows what would be written."""
        out = run_ok(server, ["import", "-d", str(tmp_path), "--dry-run"], capsys)
        assert "create" in out
        assert "Daily Report" in out
        # No files should be written
        assert not list(tmp_path.glob("*.json"))

    def test_create_files(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """import creates JSON files for each workflow."""
        out = run_ok(server, ["import", "-d", str(tmp_path)], capsys)
        assert "created" in out.lower()
        files = list(tmp_path.glob("*.json"))
        assert len(files) >= 1
        # Verify file content
        data = json.loads(files[0].read_text())
        assert "id" in data
        assert "nodes" in data

    def test_skip_up_to_date(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """import skips files that are already up to date."""
        # First import
        run_ok(server, ["import", "-d", str(tmp_path)], capsys)
        # Second import should skip
        out = run_ok(server, ["import", "-d", str(tmp_path)], capsys)
        assert "skip" in out.lower()

    def test_filter_by_ids(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """import --ids filters to specific workflows."""
        out = run_ok(server, ["import", "-d", str(tmp_path), "--ids", "wf-1"], capsys)
        assert "Daily Report" in out
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["id"] == "wf-1"
