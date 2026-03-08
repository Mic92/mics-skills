"""Configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_WEBUI_PORT = 8745


@dataclass
class Config:
    """Tasker CLI configuration."""

    host: str
    webui_port: int
    adb_port: str | None

    @classmethod
    def from_env(
        cls,
        host_override: str | None = None,
        port_override: int | None = None,
    ) -> Config:
        """Build config from environment variables and CLI overrides."""
        host = (
            host_override
            if host_override is not None
            else os.environ.get("TASKER_HOST", "")
        )
        if not host:
            msg = (
                "No host specified. Set TASKER_HOST or use --host.\n"
                "Example: export TASKER_HOST=192.168.1.100"
            )
            raise SystemExit(msg)

        if port_override is not None:
            webui_port = port_override
        else:
            raw_port = os.environ.get("TASKER_WEBUI_PORT", str(DEFAULT_WEBUI_PORT))
            try:
                webui_port = int(raw_port)
            except ValueError:
                msg = f"Invalid TASKER_WEBUI_PORT: {raw_port!r} is not an integer"
                raise SystemExit(msg) from None
        adb_port = os.environ.get("TASKER_ADB_PORT")

        return cls(host=host, webui_port=webui_port, adb_port=adb_port)

    @property
    def base_url(self) -> str:
        """WebUI base URL."""
        return f"http://{self.host}:{self.webui_port}"
