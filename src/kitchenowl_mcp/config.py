"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    kitchenowl_url: str
    kitchenowl_token: str | None
    household_id: int | None
    mcp_host: str
    mcp_port: int
    mcp_path: str
    mcp_server_token: str | None
    mcp_base_url: str | None = None
    mcp_secret_key: str = ""
    mcp_data_dir: str = "."

    @classmethod
    def from_env(cls) -> Settings:
        url = os.environ.get("KITCHENOWL_URL", "").strip()
        token = os.environ.get("KITCHENOWL_TOKEN", "").strip()
        base_url = os.environ.get("MCP_BASE_URL", "").strip()
        secret_key = os.environ.get("MCP_SECRET_KEY", "").strip()
        # With MCP_BASE_URL set, users log in with their own KitchenOwl account instead.
        required = [("KITCHENOWL_URL", url)]
        required.append(("MCP_SECRET_KEY", secret_key) if base_url else ("KITCHENOWL_TOKEN", token))
        missing = [name for name, value in required if not value]
        if missing:
            raise SystemExit(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                "Set KITCHENOWL_URL to your KitchenOwl instance "
                "(e.g. https://kitchenowl.example.com) and KITCHENOWL_TOKEN to a "
                "long-lived token (KitchenOwl app: Profile -> Sessions), or MCP_BASE_URL "
                "and MCP_SECRET_KEY for per-user login."
            )

        household_raw = os.environ.get("KITCHENOWL_HOUSEHOLD_ID", "").strip()
        return cls(
            kitchenowl_url=url,
            kitchenowl_token=token or None,
            household_id=int(household_raw) if household_raw else None,
            mcp_host=os.environ.get("MCP_HOST", "0.0.0.0"),
            mcp_port=int(os.environ.get("MCP_PORT", "8000")),
            mcp_path=os.environ.get("MCP_PATH", "/mcp"),
            mcp_server_token=os.environ.get("MCP_SERVER_TOKEN", "").strip() or None,
            mcp_base_url=base_url or None,
            mcp_secret_key=secret_key,
            mcp_data_dir=os.environ.get("MCP_DATA_DIR", "."),
        )
