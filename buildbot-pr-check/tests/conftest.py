import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests hermetic: no ambient tokens."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
