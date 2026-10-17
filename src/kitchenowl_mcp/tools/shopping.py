"""Shopping list and item catalog tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from kitchenowl_mcp.tools import get_client, kitchenowl_tool


def _slim_item(item: dict[str, Any]) -> dict[str, Any]:
    category = item.get("category")
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description") or "",
        "category": category.get("name") if isinstance(category, dict) else category,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @kitchenowl_tool
    async def list_shopping_lists(household_id: int | None = None) -> list[dict[str, Any]]:
        """List the shopping lists of a household."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        lists = await client.request("GET", f"/household/{hid}/shoppinglist")
        return [{"id": sl.get("id"), "name": sl.get("name")} for sl in lists]

    @mcp.tool
    @kitchenowl_tool
    async def create_shopping_list(name: str, household_id: int | None = None) -> dict[str, Any]:
        """Create a new shopping list in a household."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        result = await client.request("POST", f"/household/{hid}/shoppinglist", json={"name": name})
        return {"id": result.get("id"), "name": result.get("name")} if result else {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def rename_shopping_list(
        list_id: int, name: str, household_id: int | None = None
    ) -> str:
        """Rename a shopping list."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request(
            "POST", f"/shoppinglist/{list_id}", json={"name": name}
        )
        return f"Shopping list {list_id} renamed to '{name}'."

    @mcp.tool
    @kitchenowl_tool
    async def delete_shopping_list(list_id: int, household_id: int | None = None) -> str:
        """Delete a shopping list. This cannot be undone."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request("DELETE", f"/shoppinglist/{list_id}")
        return f"Shopping list {list_id} deleted."

    @mcp.tool
    @kitchenowl_tool
    async def get_shopping_list_items(
        list_id: int, household_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Get the items currently on a shopping list (i.e. still to be bought).

        The description field typically holds the quantity or a note (e.g. "500g").
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        items = await client.request("GET", f"/shoppinglist/{list_id}/items")
        return [_slim_item(i) for i in items]

    @mcp.tool
    @kitchenowl_tool
    async def add_shopping_list_item(
        list_id: int,
        name: str,
        description: str = "",
        household_id: int | None = None,
    ) -> dict[str, Any]:
        """Add an item to a shopping list by name.

        If no catalog item with that name exists yet, KitchenOwl creates one.
        Use description for the quantity or a note (e.g. "2x", "500g").
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        result = await client.request(
            "POST", f"/shoppinglist/{list_id}/add-item-by-name", json=payload
        )
        return _slim_item(result) if isinstance(result, dict) else {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def update_shopping_list_item(
        list_id: int,
        item_id: int,
        description: str,
        household_id: int | None = None,
    ) -> str:
        """Update the description (quantity/note) of an item on a shopping list."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request(
            "POST",
            f"/shoppinglist/{list_id}/item/{item_id}",
            json={"description": description},
        )
        return f"Item {item_id} updated."

    @mcp.tool
    @kitchenowl_tool
    async def remove_shopping_list_items(
        list_id: int,
        item_ids: list[int],
        household_id: int | None = None,
    ) -> str:
        """Remove items from a shopping list.

        In KitchenOwl removing an item means it was purchased (there is no separate
        check/uncheck state); removal is recorded in the purchase history and drives
        future suggestions.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request(
            "DELETE",
            f"/shoppinglist/{list_id}/items",
            json={"items": [{"item_id": item_id} for item_id in item_ids]},
        )
        return f"Removed {len(item_ids)} item(s) from list {list_id}."

    @mcp.tool
    @kitchenowl_tool
    async def get_recent_items(
        list_id: int, household_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Get recently purchased/removed items of a shopping list."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        items = await client.request(
            "GET", f"/shoppinglist/{list_id}/recent-items"
        )
        return [_slim_item(i) for i in items]

    @mcp.tool
    @kitchenowl_tool
    async def get_suggested_items(
        list_id: int, household_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Get KitchenOwl's suggested items for a shopping list (based on purchase history)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        items = await client.request(
            "GET", f"/shoppinglist/{list_id}/suggested-items"
        )
        return [_slim_item(i) for i in items]

    @mcp.tool
    @kitchenowl_tool
    async def add_recipe_items_to_shopping_list(
        list_id: int,
        recipe_id: int,
        household_id: int | None = None,
    ) -> str:
        """Add all non-optional ingredients of a recipe to a shopping list."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        recipe = await client.request("GET", f"/recipe/{recipe_id}")
        items = [
            {"id": i["id"], "description": i.get("description") or ""}
            for i in recipe.get("items", []) or []
            if not i.get("optional")
        ]
        if not items:
            return f"Recipe '{recipe.get('name')}' has no non-optional ingredients to add."
        await client.request(
            "POST",
            f"/shoppinglist/{list_id}/recipeitems",
            json={"items": items},
        )
        return (
            f"Added {len(items)} ingredient(s) of recipe '{recipe.get('name')}' "
            f"to shopping list {list_id}."
        )

    @mcp.tool
    @kitchenowl_tool
    async def search_items(query: str, household_id: int | None = None) -> list[dict[str, Any]]:
        """Search the household's item catalog by name."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        items = await client.request(
            "GET", f"/household/{hid}/item/search", params={"query": query}
        )
        return [_slim_item(i) for i in items]

    @mcp.tool
    @kitchenowl_tool
    async def update_item(
        item_id: int,
        name: str | None = None,
        category_id: int | None = None,
        icon: str | None = None,
        household_id: int | None = None,
    ) -> str:
        """Update a catalog item (rename, assign a category so lists sort correctly, set icon)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if category_id is not None:
            payload["category"] = {"id": category_id}
        if icon is not None:
            payload["icon"] = icon
        if not payload:
            return "Nothing to update — pass name, category_id, or icon."
        await client.request("POST", f"/item/{item_id}", json=payload)
        return f"Item {item_id} updated."
