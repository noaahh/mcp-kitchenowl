"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    kitchenowl_url: str
    kitchenowl_token: str
    household_id: int | None
    mcp_host: str
    mcp_port: int
    mcp_path: str
    mcp_server_token: str | None

    @classmethod
    def from_env(cls) -> Settings:
        url = os.environ.get("KITCHENOWL_URL", "").strip()
        token = os.environ.get("KITCHENOWL_TOKEN", "").strip()
        missing = [
            name
            for name, value in (("KITCHENOWL_URL", url), ("KITCHENOWL_TOKEN", token))
            if not value
        ]
        if missing:
            raise SystemExit(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                "Set KITCHENOWL_URL to your KitchenOwl instance "
                "(e.g. https://kitchenowl.example.com) and KITCHENOWL_TOKEN to a "
                "long-lived token (KitchenOwl app: Profile -> Sessions)."
            )

        household_raw = os.environ.get("KITCHENOWL_HOUSEHOLD_ID", "").strip()
        return cls(
            kitchenowl_url=url,
            kitchenowl_token=token,
            household_id=int(household_raw) if household_raw else None,
            mcp_host=os.environ.get("MCP_HOST", "0.0.0.0"),
            mcp_port=int(os.environ.get("MCP_PORT", "8000")),
            mcp_path=os.environ.get("MCP_PATH", "/mcp"),
            mcp_server_token=os.environ.get("MCP_SERVER_TOKEN", "").strip() or None,
        )
