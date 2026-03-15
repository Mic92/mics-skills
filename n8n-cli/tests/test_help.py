"""Help output tests."""

from unittest.mock import patch

import pytest

from n8n_cli.main import main


class TestHelp:
    def test_top_level_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["n8n-cli", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "credential" in out
        assert "workflow" in out
        assert "execution" in out
        assert "tag" in out
        assert "datatable" in out
        assert "raw" in out
        assert "test" in out
        assert "import" in out
        assert "apply" in out

    def test_subcommand_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["n8n-cli", "credential", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "list" in out
        assert "get" in out
        assert "schema" in out
