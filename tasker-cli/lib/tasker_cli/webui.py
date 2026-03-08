"""WebUI HTTP client for Tasker's action editor API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable


class WebUIError(Exception):
    """Error communicating with the Tasker WebUI."""


# JSON type aliases for the untyped WebUI responses
type JsonValue = (
    str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
)


@runtime_checkable
class TaskEditor(Protocol):
    """Protocol for editing actions in a Tasker task.

    Implemented by WebUIClient (real) and test Recording/Replay clients.
    """

    def get_actions(self) -> list[dict[str, JsonValue]]: ...
    def append_action(self, action: dict[str, JsonValue]) -> JsonValue: ...
    def delete_action(self, index: int) -> JsonValue: ...


class WebUIClient:
    """HTTP client for the Tasker WebUI API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: dict[str, JsonValue] | None = None,
    ) -> JsonValue:
        """Make an HTTP request to the WebUI."""
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"} if body else {}

        req = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                raw = resp.read().decode()
                if not raw:
                    return None
                return json.loads(raw)  # type: ignore[no-any-return]
        except urllib.error.URLError as e:
            msg = f"WebUI request failed: {path}: {e}"
            raise WebUIError(msg) from e

    def ping(self) -> bool:
        """Check if WebUI is reachable."""
        try:
            self._request("/ping")
        except WebUIError:
            return False
        return True

    def get_actions(self) -> list[dict[str, JsonValue]]:
        """Get all actions in the currently-edited task."""
        result = self._request("/actions")
        if result is None:
            return []
        return result if isinstance(result, list) else []  # type: ignore[return-value]

    def append_action(self, action: dict[str, JsonValue]) -> JsonValue:
        """Append an action to the end of the task."""
        return self._request("/actions", method="PATCH", data=action)

    def delete_action(self, index: int) -> JsonValue:
        """Delete an action at the given index."""
        return self._request(f"/delete?index={index}")

    def get_action_specs(self) -> JsonValue:
        """Get all action spec definitions."""
        return self._request("/action_specs")

    def get_arg_specs(self) -> JsonValue:
        """Get argument type map."""
        return self._request("/arg_specs")

    def get_category_specs(self) -> JsonValue:
        """Get action category list."""
        return self._request("/category_specs")
