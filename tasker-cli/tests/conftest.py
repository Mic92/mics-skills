"""Shared test fixtures and record/replay infrastructure for tasker-cli."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tasker_cli.specs import SpecsCache
from tasker_cli.webui import JsonValue, WebUIClient, WebUIError

if TYPE_CHECKING:
    from collections.abc import Iterator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> object:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def specs_cache() -> SpecsCache:
    """SpecsCache loaded from recorded fixtures."""
    return SpecsCache.from_raw(
        action_specs_raw=load_fixture("action_specs.json"),  # type: ignore[arg-type]
        arg_specs_raw=load_fixture("arg_specs.json"),  # type: ignore[arg-type]
        category_specs_raw=load_fixture("category_specs.json"),  # type: ignore[arg-type]
    )


# --- Record/Replay infrastructure ---


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --record and --host CLI options for live recording."""
    parser.addoption(
        "--record",
        action="store_true",
        default=False,
        help="Record responses from a live phone instead of replaying fixtures",
    )
    parser.addoption(
        "--host",
        default=None,
        help="Phone IP for recording (requires --record)",
    )


class RecordingClient:
    """Wraps a real WebUIClient, records all call results to a log."""

    def __init__(self, real: WebUIClient) -> None:
        self._real = real
        self.log: list[dict[str, Any]] = []

    def _record(self, method: str, args: dict[str, Any], result: object) -> None:
        self.log.append({"method": method, "args": args, "result": result})

    def get_actions(self) -> list[dict[str, JsonValue]]:
        result = self._real.get_actions()
        self._record("get_actions", {}, result)
        return result

    def append_action(self, action: dict[str, JsonValue]) -> JsonValue:
        result = self._real.append_action(action)
        self._record("append_action", {"action": action}, result)
        return result

    def delete_action(self, index: int) -> JsonValue:
        result = self._real.delete_action(index)
        self._record("delete_action", {"index": index}, result)
        return result

    def save(self, path: Path) -> None:
        """Save the recorded log to a JSON fixture."""
        path.write_text(json.dumps(self.log, indent=2), encoding="utf-8")


class ReplayClient:
    """Replays recorded responses in order. Raises on unexpected calls."""

    def __init__(self, log: list[dict[str, Any]]) -> None:
        self._log = list(log)
        self._pos = 0

    def _next(self, method: str) -> JsonValue:
        if self._pos >= len(self._log):
            msg = f"ReplayClient: no more recorded calls, got {method}"
            raise WebUIError(msg)
        entry = self._log[self._pos]
        if entry["method"] != method:
            msg = (
                f"ReplayClient: expected {entry['method']} "
                f"at position {self._pos}, got {method}"
            )
            raise WebUIError(msg)
        self._pos += 1
        return entry["result"]  # type: ignore[no-any-return]

    def get_actions(self) -> list[dict[str, JsonValue]]:
        return self._next("get_actions")  # type: ignore[return-value]

    def append_action(self, _action: dict[str, JsonValue]) -> JsonValue:
        return self._next("append_action")

    def delete_action(self, _index: int) -> JsonValue:
        return self._next("delete_action")


def _session_fixture(
    request: pytest.FixtureRequest,
    name: str,
) -> Iterator[RecordingClient | ReplayClient]:
    """Record or replay a named WebUI session."""
    record: bool = request.config.getoption("--record")
    fixture_path = FIXTURES_DIR / f"{name}.json"

    if record:
        host: str | None = request.config.getoption("--host")
        if not host:
            pytest.skip("--record requires --host")
        real = WebUIClient(f"http://{host}:8745")
        client = RecordingClient(real)
        yield client
        client.save(fixture_path)
    else:
        if not fixture_path.exists():
            pytest.skip(f"No recorded fixture: {fixture_path}")
        log = json.loads(fixture_path.read_text(encoding="utf-8"))
        yield ReplayClient(log)


@pytest.fixture
def deploy_client(
    request: pytest.FixtureRequest,
) -> Iterator[RecordingClient | ReplayClient]:
    """WebUI client for deploy-to-empty tests."""
    yield from _session_fixture(request, "session_deploy")


@pytest.fixture
def replace_client(
    request: pytest.FixtureRequest,
) -> Iterator[RecordingClient | ReplayClient]:
    """WebUI client for replace tests."""
    yield from _session_fixture(request, "session_replace")


@pytest.fixture
def append_client(
    request: pytest.FixtureRequest,
) -> Iterator[RecordingClient | ReplayClient]:
    """WebUI client for append tests."""
    yield from _session_fixture(request, "session_append")
