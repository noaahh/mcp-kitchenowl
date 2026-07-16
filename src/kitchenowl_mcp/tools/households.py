"""Household tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from kitchenowl_mcp.tools import get_client, kitchenowl_tool


def _slim_member(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": member.get("id"),
        "name": member.get("name"),
        "username": member.get("username"),
        "admin": member.get("admin"),
        "owner": member.get("owner"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @kitchenowl_tool
    async def list_households() -> list[dict[str, Any]]:
        """List all KitchenOwl households the configured user belongs to.

        Returns id and name per household. Use the id as household_id in other tools.
        """
        households = await get_client().request("GET", "/household")
        return [
            {
                "id": h.get("id"),
                "name": h.get("name"),
                "member_count": len(h.get("member", []) or []),
            }
            for h in households
        ]

    @mcp.tool
    @kitchenowl_tool
    async def get_household(household_id: int | None = None) -> dict[str, Any]:
        """Get a household including its members.

        Member ids are needed for expense tools (paid_by / paid_for).
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        household = await client.request("GET", f"/household/{hid}")
        return {
            "id": household.get("id"),
            "name": household.get("name"),
            "language": household.get("language"),
            "planner_feature": household.get("planner_feature"),
            "expenses_feature": household.get("expenses_feature"),
            "members": [_slim_member(m) for m in household.get("member", []) or []],
        }
