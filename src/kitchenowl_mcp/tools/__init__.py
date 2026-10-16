"""Tool registration and shared helpers."""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

from kitchenowl_mcp.client import KitchenOwlClient, KitchenOwlError

_client: KitchenOwlClient | None = None
_kitchenowl_url = ""
# ponytail: one client per logged-in user, never evicted; fine for a household or two
_user_clients: dict[str, KitchenOwlClient] = {}


def set_client(client: KitchenOwlClient | None) -> None:
    global _client
    _client = client


def set_kitchenowl_url(url: str) -> None:
    global _kitchenowl_url
    _kitchenowl_url = url


async def close_user_clients() -> None:
    for client in _user_clients.values():
        await client.aclose()
    _user_clients.clear()


def get_client() -> KitchenOwlClient:
    """The logged-in user's client when the request carries a KitchenOwl login, else the env one."""
    token = get_access_token()
    ko_token = token.claims.get("kitchenowl_token") if token else None
    if ko_token:
        if ko_token not in _user_clients:
            _user_clients[ko_token] = KitchenOwlClient(_kitchenowl_url, ko_token)
        return _user_clients[ko_token]
    if _client is None:
        raise ToolError("KitchenOwl client is not initialized (server not started).")
    return _client


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def kitchenowl_tool(func: F) -> F:
    """Convert KitchenOwlError into ToolError with LLM-actionable messages."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except KitchenOwlError as exc:
            if exc.status_code in (401, 422):
                raise ToolError(
                    f"KitchenOwl rejected the token ({exc.status_code}: {exc.message}). "
                    "Check KITCHENOWL_TOKEN — mint a long-lived token in the KitchenOwl "
                    "app under Profile -> Sessions."
                ) from exc
            if exc.status_code == 403:
                raise ToolError(
                    f"Forbidden (403: {exc.message}). The token's user may not be a member "
                    "of this household — check household_id with list_households."
                ) from exc
            if exc.status_code == 404:
                raise ToolError(
                    f"Not found (404: {exc.message}). Check the id — use the list_*/search_* "
                    "tools to discover valid ids."
                ) from exc
            if exc.status_code is None:
                raise ToolError(exc.message) from exc
            raise ToolError(f"KitchenOwl error ({exc.status_code}): {exc.message}") from exc

    return wrapper  # type: ignore[return-value]


def register_all(mcp: FastMCP) -> None:
    from kitchenowl_mcp.tools import expenses, households, planner, recipes, shopping

    for module in (households, shopping, recipes, planner, expenses):
        module.register(mcp)
