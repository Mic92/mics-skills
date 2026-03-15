"""Error handling tests."""

from unittest.mock import patch

import pytest

from n8n_cli.main import main


class TestErrors:
    def test_missing_credentials(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing API URL/key produces a ConfigError, not a traceback."""
        env = {"N8N_API_URL": "", "N8N_API_KEY": ""}
        with patch.dict("os.environ", env, clear=False):
            with patch("sys.argv", ["n8n-cli", "credential", "list"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "N8N_API_URL" in err

    def test_unknown_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unknown top-level command exits with code 2 (argparse error)."""
        with patch.dict("os.environ", {"N8N_API_URL": "x", "N8N_API_KEY": "x"}):
            with patch("sys.argv", ["n8n-cli", "bogus"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 2
