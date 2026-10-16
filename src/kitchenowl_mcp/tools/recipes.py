"""Recipe tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from kitchenowl_mcp.client import KitchenOwlError
from kitchenowl_mcp.tools import get_client, kitchenowl_tool


def _slim_recipe_summary(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": recipe.get("id"),
        "name": recipe.get("name"),
        "time": recipe.get("time"),
        "yields": recipe.get("yields"),
        "tags": [t.get("name") for t in recipe.get("tags", []) or []],
    }


def _slim_recipe_full(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        **_slim_recipe_summary(recipe),
        "description": recipe.get("description") or "",
        "cook_time": recipe.get("cook_time"),
        "prep_time": recipe.get("prep_time"),
        "source": recipe.get("source") or "",
        "items": [
            {
                "id": i.get("id"),
                "name": i.get("name"),
                "description": i.get("description") or "",
                "optional": bool(i.get("optional")),
            }
            for i in recipe.get("items", []) or []
        ],
    }


def _recipe_payload(
    name: str | None = None,
    description: str | None = None,
    time: int | None = None,
    cook_time: int | None = None,
    prep_time: int | None = None,
    yields: int | None = None,
    source: str | None = None,
    items: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in (
        ("name", name),
        ("description", description),
        ("time", time),
        ("cook_time", cook_time),
        ("prep_time", prep_time),
        ("yields", yields),
        ("source", source),
    ):
        if value is not None:
            payload[key] = value
    if items is not None:
        payload["items"] = [
            {
                "name": i["name"],
                "description": i.get("description") or "",
                "optional": bool(i.get("optional")),
            }
            for i in items
        ]
    if tags is not None:
        payload["tags"] = list(tags)
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @kitchenowl_tool
    async def list_recipes(household_id: int | None = None) -> list[dict[str, Any]]:
        """List all recipes of a household (compact; use get_recipe for details)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        recipes = await client.request("GET", f"/household/{hid}/recipe")
        return [_slim_recipe_summary(r) for r in recipes]

    @mcp.tool
    @kitchenowl_tool
    async def list_tags(household_id: int | None = None) -> list[str]:
        """List the household's recipe tags (reuse these names in create/update_recipe)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        return [t["name"] for t in await client.request("GET", f"/household/{hid}/tag")]

    @mcp.tool
    @kitchenowl_tool
    async def search_recipes(query: str, household_id: int | None = None) -> list[dict[str, Any]]:
        """Search the household's recipes by name."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        recipes = await client.request(
            "GET", f"/household/{hid}/recipe/search", params={"query": query}
        )
        return [_slim_recipe_summary(r) for r in recipes]

    @mcp.tool
    @kitchenowl_tool
    async def get_recipe(recipe_id: int, household_id: int | None = None) -> dict[str, Any]:
        """Get a recipe with its full description and ingredient list."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        recipe = await client.request("GET", f"/recipe/{recipe_id}")
        return _slim_recipe_full(recipe)

    @mcp.tool
    @kitchenowl_tool
    async def create_recipe(
        name: str,
        description: str = "",
        time: int | None = None,
        cook_time: int | None = None,
        prep_time: int | None = None,
        yields: int | None = None,
        source: str = "",
        items: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        household_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a recipe.

        description is the instruction text (markdown supported). time/cook_time/prep_time
        are minutes, yields is the number of servings. items is a list of ingredients:
        [{"name": "Flour", "description": "500g", "optional": false}, ...].
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload = _recipe_payload(
            name, description, time, cook_time, prep_time, yields, source, items or [], tags or []
        )
        result = await client.request("POST", f"/household/{hid}/recipe", json=payload)
        return _slim_recipe_full(result) if isinstance(result, dict) else {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def update_recipe(
        recipe_id: int,
        name: str | None = None,
        description: str | None = None,
        time: int | None = None,
        cook_time: int | None = None,
        prep_time: int | None = None,
        yields: int | None = None,
        source: str | None = None,
        items: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        household_id: int | None = None,
    ) -> str:
        """Update a recipe. Only the fields you pass are changed.

        Note: passing items or tags replaces the recipe's full ingredient/tag list,
        so include all ingredients/tags you want to keep (fetch with get_recipe first).
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload = _recipe_payload(
            name, description, time, cook_time, prep_time, yields, source, items, tags
        )
        if not payload:
            return "Nothing to update — pass at least one field."
        await client.request("POST", f"/recipe/{recipe_id}", json=payload)
        return f"Recipe {recipe_id} updated."

    @mcp.tool
    @kitchenowl_tool
    async def delete_recipe(recipe_id: int, household_id: int | None = None) -> str:
        """Delete a recipe. This cannot be undone."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request("DELETE", f"/recipe/{recipe_id}")
        return f"Recipe {recipe_id} deleted."

    @mcp.tool
    @kitchenowl_tool
    async def import_recipe_from_url(
        url: str,
        save: bool = False,
        household_id: int | None = None,
    ) -> dict[str, Any]:
        """Import (scrape) a recipe from a web URL.

        By default returns the scraped draft for review without saving. Pass save=true
        to store it as a new recipe in the household.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        try:
            scraped = await client.request(
                "GET", f"/household/{hid}/recipe/scrape", params={"url": url}
            )
        except KitchenOwlError as exc:
            if exc.status_code == 405:
                scraped = await client.request(
                    "POST", f"/household/{hid}/recipe/scrape", json={"url": url}
                )
            else:
                raise
        recipe = scraped.get("recipe", scraped) if isinstance(scraped, dict) else {}
        draft = {
            "name": recipe.get("name"),
            "description": recipe.get("description") or "",
            "time": recipe.get("time"),
            "cook_time": recipe.get("cook_time"),
            "prep_time": recipe.get("prep_time"),
            "yields": recipe.get("yields"),
            "source": recipe.get("source") or url,
            "items": [
                {
                    "name": i.get("name"),
                    "description": i.get("description") or "",
                    "optional": bool(i.get("optional")),
                }
                for i in recipe.get("items", []) or []
            ],
        }
        if not save:
            return {"saved": False, "draft": draft}
        payload = {**draft, "tags": []}
        created = await client.request("POST", f"/household/{hid}/recipe", json=payload)
        result = _slim_recipe_full(created) if isinstance(created, dict) else draft
        return {"saved": True, "recipe": result}
