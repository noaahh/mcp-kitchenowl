"""Meal planner tools."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from fastmcp import FastMCP

from kitchenowl_mcp.tools import get_client, kitchenowl_tool


def _iso_date_to_epoch_ms(value: str) -> int:
    parsed = date.fromisoformat(value)
    return int(datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC).timestamp() * 1000)


def _epoch_ms_to_iso(value: Any) -> str | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()


def _slim_plan_entry(entry: dict[str, Any]) -> dict[str, Any]:
    recipe = entry.get("recipe", entry) or {}
    return {
        "recipe_id": recipe.get("id"),
        "recipe_name": recipe.get("name"),
        "day": entry.get("day"),
        "cooking_date": _epoch_ms_to_iso(entry.get("cooking_date")),
        "yields": entry.get("yields"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @kitchenowl_tool
    async def get_meal_plan(household_id: int | None = None) -> list[dict[str, Any]]:
        """Get the household's current meal plan (planned recipes with day/date)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        entries = await client.request("GET", f"/household/{hid}/planner")
        return [_slim_plan_entry(e) for e in entries]

    @mcp.tool
    @kitchenowl_tool
    async def add_recipe_to_plan(
        recipe_id: int,
        cooking_date: str | None = None,
        day: int | None = None,
        yields: int | None = None,
        household_id: int | None = None,
    ) -> str:
        """Add a recipe to the meal plan.

        cooking_date is an ISO date (YYYY-MM-DD). Alternatively pass day as a weekday
        number (0=Monday .. 6=Sunday). Omit both to plan without a specific day.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload: dict[str, Any] = {"recipe_id": recipe_id}
        if cooking_date is not None:
            payload["cooking_date"] = _iso_date_to_epoch_ms(cooking_date)
        if day is not None:
            payload["day"] = day
        if yields is not None:
            payload["yields"] = yields
        await client.request("POST", f"/household/{hid}/planner/recipe", json=payload)
        return f"Recipe {recipe_id} added to the meal plan."

    @mcp.tool
    @kitchenowl_tool
    async def remove_recipe_from_plan(
        recipe_id: int,
        cooking_date: str | None = None,
        day: int | None = None,
        household_id: int | None = None,
    ) -> str:
        """Remove a recipe from the meal plan.

        Pass the same cooking_date (YYYY-MM-DD) or day the entry was planned for;
        omit both to remove an entry planned without a specific day.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload: dict[str, Any] = {}
        if cooking_date is not None:
            payload["cooking_date"] = _iso_date_to_epoch_ms(cooking_date)
        if day is not None:
            payload["day"] = day
        await client.request(
            "DELETE", f"/household/{hid}/planner/recipe/{recipe_id}", json=payload or None
        )
        return f"Recipe {recipe_id} removed from the meal plan."

    @mcp.tool
    @kitchenowl_tool
    async def get_recipe_suggestions(
        kind: Literal["suggested", "recent"] = "suggested",
        household_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get recipe suggestions for meal planning.

        kind="suggested" returns KitchenOwl's suggestions, kind="recent" returns
        recently cooked recipes.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        path = "suggested-recipes" if kind == "suggested" else "recent-recipes"
        recipes = await client.request("GET", f"/household/{hid}/planner/{path}")
        return [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "time": r.get("time"),
                "tags": [t.get("name") for t in r.get("tags", []) or []],
            }
            for r in recipes
        ]
