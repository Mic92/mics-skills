"""Apply command tests."""

import json
from pathlib import Path

import pytest

from tests.conftest import WORKFLOW_1, run_fail, run_ok


class TestApplyCommand:
    def test_create_new(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """apply creates workflow when local file has no ID."""
        wf = {"name": "Brand New", "nodes": [], "connections": {}}
        (tmp_path / "new.json").write_text(json.dumps(wf))
        out = run_ok(server, ["apply", "-d", str(tmp_path)], capsys)
        assert "create" in out.lower()
        # File should be updated with server-assigned ID
        data = json.loads((tmp_path / "new.json").read_text())
        assert data.get("id") is not None

    def test_dry_run(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """apply --dry-run previews without changes."""
        wf = {"name": "Dry Run Test", "nodes": [], "connections": {}}
        (tmp_path / "dry.json").write_text(json.dumps(wf))
        out = run_ok(server, ["apply", "-d", str(tmp_path), "--dry-run"], capsys)
        assert "create" in out.lower()
        # File should NOT be updated
        data = json.loads((tmp_path / "dry.json").read_text())
        assert "id" not in data

    def test_skip_unchanged(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """apply skips workflows that match remote."""
        (tmp_path / "existing.json").write_text(json.dumps(WORKFLOW_1))
        out = run_ok(server, ["apply", "-d", str(tmp_path)], capsys)
        assert "skip" in out.lower()

    def test_empty_dir(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """apply with empty directory prints message."""
        out = run_ok(server, ["apply", "-d", str(tmp_path)], capsys)
        assert "No workflow files found" in out

    def test_missing_dir(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """apply with nonexistent directory shows error."""
        err = run_fail(server, ["apply", "-d", str(tmp_path / "nope")], capsys)
        assert "not found" in err.lower() or "Directory" in err
