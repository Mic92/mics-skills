"""n8n REST API client."""

import json
import urllib.error
import urllib.request
from typing import Any

from n8n_cli.errors import APIError, ConnectionError_


class Client:
    """Minimal n8n REST API client using only stdlib."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        url = base_url.rstrip("/")
        if not url.endswith("/api/v1"):
            url += "/api/v1"
        self.base_url = url
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.base_url}{path}"
        data = None
        headers: dict[str, str] = {
            "X-N8N-API-KEY": self.api_key,
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode() if e.fp else ""
            msg = body_text
            try:
                parsed = json.loads(body_text)
                if "message" in parsed:
                    msg = parsed["message"]
            except (json.JSONDecodeError, KeyError):
                pass
            raise APIError(e.code, msg) from e
        except urllib.error.URLError as e:
            raise ConnectionError_(str(e.reason)) from e

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, body)

    def put(self, path: str, body: Any = None) -> Any:
        return self._request("PUT", path, body)

    def patch(self, path: str, body: Any = None) -> Any:
        return self._request("PATCH", path, body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)
