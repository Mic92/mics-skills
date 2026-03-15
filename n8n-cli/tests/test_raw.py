"""Raw command tests."""

import json
from pathlib import Path

import pytest

from tests.conftest import run_fail, run_ok


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

    def test_unsupported_method(
        self,
        server: tuple[str, int],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        err = run_fail(server, ["raw", "TRACE", "/foo"], capsys)
        assert "Unsupported HTTP method" in err
