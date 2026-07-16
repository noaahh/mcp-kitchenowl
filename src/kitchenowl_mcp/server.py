"""FastMCP server exposing KitchenOwl tools over streamable HTTP."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.lifespan import lifespan

from kitchenowl_mcp.client import KitchenOwlClient
from kitchenowl_mcp.config import Settings
from kitchenowl_mcp.tools import register_all, set_client

INSTRUCTIONS = (
    "Tools for managing a KitchenOwl household: shopping lists, recipes, meal planning, "
    "and shared expenses. Removing a shopping list item means it was purchased — "
    "KitchenOwl has no separate check/uncheck state. Household-scoped tools accept an "
    "optional household_id; if the user has a single household it is picked automatically."
)


@lifespan
async def _kitchenowl_lifespan(server: FastMCP):
    settings = Settings.from_env()
    client = KitchenOwlClient(
        settings.kitchenowl_url,
        settings.kitchenowl_token,
        default_household_id=settings.household_id,
    )
    set_client(client)
    try:
        yield {}
    finally:
        set_client(None)
        await client.aclose()


def create_server(*, with_lifespan: bool = True, auth: object | None = None) -> FastMCP:
    mcp = FastMCP(
        name="KitchenOwl",
        instructions=INSTRUCTIONS,
        lifespan=_kitchenowl_lifespan if with_lifespan else None,
        auth=auth,
    )
    register_all(mcp)
    return mcp


def main() -> None:
    settings = Settings.from_env()
    auth = None
    if settings.mcp_server_token:
        auth = StaticTokenVerifier(
            tokens={settings.mcp_server_token: {"client_id": "kitchenowl-mcp", "scopes": []}}
        )
    mcp = create_server(auth=auth)
    mcp.run(
        transport="http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        path=settings.mcp_path,
    )


if __name__ == "__main__":
    main()
