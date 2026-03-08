"""Tests for deploy logic against real/recorded WebUI responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from tasker_cli.main import _deploy_actions
from tasker_cli.webui import WebUIError

if TYPE_CHECKING:
    from tasker_cli.specs import SpecsCache
    from tasker_cli.webui import TaskEditor

FLASH_HELLO = {"action": "Flash", "args": {"Text": "hello"}}
FLASH_WORLD = {"action": "Flash", "args": {"Text": "world"}}


class TestDeployRecorded:
    """Tests that record/replay against the real WebUI."""

    def test_deploy_to_empty(
        self,
        deploy_client: TaskEditor,
        specs_cache: SpecsCache,
    ) -> None:
        """Deploy a Flash action to an empty task, verify, clean up."""
        _deploy_actions(deploy_client, specs_cache, [FLASH_HELLO], append=False)

        actions = deploy_client.get_actions()
        assert len(actions) == 1
        assert actions[0]["code"] == 548
        args = actions[0]["args"]
        assert isinstance(args, list)
        text_arg = next(a for a in args if isinstance(a, dict) and a["id"] == 0)
        assert text_arg["value"] == "hello"

        # Clean up
        deploy_client.delete_action(0)
        assert deploy_client.get_actions() == []

    def test_replace_clears_existing(
        self,
        replace_client: TaskEditor,
        specs_cache: SpecsCache,
    ) -> None:
        """Deploy 2 actions, then replace with 1 — should only have 1."""
        # Set up: deploy 2 actions
        _deploy_actions(
            replace_client, specs_cache, [FLASH_HELLO, FLASH_WORLD], append=False
        )
        actions = replace_client.get_actions()
        assert len(actions) == 2

        # Replace with 1
        _deploy_actions(replace_client, specs_cache, [FLASH_WORLD], append=False)
        actions = replace_client.get_actions()
        assert len(actions) == 1
        args = actions[0]["args"]
        assert isinstance(args, list)
        text_arg = next(a for a in args if isinstance(a, dict) and a["id"] == 0)
        assert text_arg["value"] == "world"

        # Clean up
        replace_client.delete_action(0)
        assert replace_client.get_actions() == []

    def test_append_keeps_existing(
        self,
        append_client: TaskEditor,
        specs_cache: SpecsCache,
    ) -> None:
        """Deploy 1 action, then append 1 — should have 2."""
        _deploy_actions(append_client, specs_cache, [FLASH_HELLO], append=False)
        actions = append_client.get_actions()
        assert len(actions) == 1

        _deploy_actions(append_client, specs_cache, [FLASH_WORLD], append=True)
        actions = append_client.get_actions()
        assert len(actions) == 2

        # First is hello, second is world
        args0 = actions[0]["args"]
        args1 = actions[1]["args"]
        assert isinstance(args0, list)
        assert isinstance(args1, list)
        text0 = next(a for a in args0 if isinstance(a, dict) and a["id"] == 0)
        text1 = next(a for a in args1 if isinstance(a, dict) and a["id"] == 0)
        assert text0["value"] == "hello"
        assert text1["value"] == "world"

        # Clean up
        append_client.delete_action(1)
        append_client.delete_action(0)
        assert append_client.get_actions() == []


class FakeClient:
    """Fake WebUI client that simulates failure at a given action index."""

    def __init__(
        self,
        existing: list[dict[str, Any]] | None = None,
        *,
        fail_at: int | None = None,
    ) -> None:
        self.existing = list(existing or [])
        self.fail_at = fail_at
        self.appended: list[dict[str, Any]] = []
        self.deleted: list[int] = []
        self._append_count = 0

    def get_actions(self) -> list[dict[str, Any]]:
        return list(self.existing)

    def append_action(self, action: dict[str, Any]) -> None:
        if self.fail_at is not None and self._append_count == self.fail_at:
            msg = "simulated WebUI failure"
            raise WebUIError(msg)
        self._append_count += 1
        self.appended.append(action)

    def delete_action(self, index: int) -> None:
        self.deleted.append(index)


EXISTING_ACTION: dict[str, Any] = {"code": 548, "args": [{"id": 0, "value": "old"}]}


class TestDeployRollback:
    """Rollback tests using a fake client — can't record real failures."""

    def test_rolls_back_on_failure(self, specs_cache: SpecsCache) -> None:
        """If the 2nd action fails, the 1st should be rolled back."""
        client = FakeClient(fail_at=1)
        with pytest.raises(SystemExit):
            _deploy_actions(
                client, specs_cache, [FLASH_HELLO, FLASH_WORLD], append=False
            )

        assert len(client.appended) == 1
        assert client.deleted == [0]

    def test_no_rollback_if_first_fails(self, specs_cache: SpecsCache) -> None:
        """If the very first action fails, nothing to roll back."""
        client = FakeClient(fail_at=0)
        with pytest.raises(SystemExit):
            _deploy_actions(client, specs_cache, [FLASH_HELLO], append=False)

        assert client.appended == []
        assert client.deleted == []

    def test_rollback_preserves_existing_in_append(
        self, specs_cache: SpecsCache
    ) -> None:
        """Rollback in append mode only deletes newly added actions."""
        client = FakeClient(existing=[EXISTING_ACTION], fail_at=1)
        with pytest.raises(SystemExit):
            _deploy_actions(
                client, specs_cache, [FLASH_HELLO, FLASH_WORLD], append=True
            )

        # Should roll back index 1 (the new one), not index 0 (existing)
        assert client.deleted == [1]
