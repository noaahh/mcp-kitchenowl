import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import BASE


@respx.mock
async def test_list_shopping_lists(mcp_client):
    respx.get(f"{BASE}/api/household/1/shoppinglist").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 1, "name": "Groceries", "items": [], "extra_field": "x"}],
        )
    )
    result = await mcp_client.call_tool("list_shopping_lists", {})
    assert result.data == [{"id": 1, "name": "Groceries"}]


@respx.mock
async def test_add_shopping_list_item_payload(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/shoppinglist/2/add-item-by-name").mock(
        return_value=httpx.Response(
            200,
            json={"id": 10, "name": "Milk", "description": "2L", "category": {"name": "Dairy"}},
        )
    )
    result = await mcp_client.call_tool(
        "add_shopping_list_item", {"list_id": 2, "name": "Milk", "description": "2L"}
    )
    assert json.loads(route.calls.last.request.content) == {"name": "Milk", "description": "2L"}
    assert result.data == {"id": 10, "name": "Milk", "description": "2L", "category": "Dairy"}


@respx.mock
async def test_remove_shopping_list_items_batch(mcp_client):
    route = respx.delete(f"{BASE}/api/household/1/shoppinglist/2/items").mock(
        return_value=httpx.Response(200, json={"msg": "DONE"})
    )
    result = await mcp_client.call_tool(
        "remove_shopping_list_items", {"list_id": 2, "item_ids": [10, 11]}
    )
    assert json.loads(route.calls.last.request.content) == {
        "items": [{"item_id": 10}, {"item_id": 11}]
    }
    assert "2 item(s)" in result.data


@respx.mock
async def test_get_shopping_list_items_slims_fields(mcp_client):
    respx.get(f"{BASE}/api/household/1/shoppinglist/2/items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 10,
                    "name": "Milk",
                    "description": "2L",
                    "category": {"id": 3, "name": "Dairy"},
                    "created_at": 1234,
                    "created_by": 1,
                    "icon": None,
                }
            ],
        )
    )
    result = await mcp_client.call_tool("get_shopping_list_items", {"list_id": 2})
    assert result.data == [{"id": 10, "name": "Milk", "description": "2L", "category": "Dairy"}]


@respx.mock
async def test_add_recipe_items_to_shopping_list_composite(mcp_client):
    respx.get(f"{BASE}/api/household/1/recipe/5").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 5,
                "name": "Pasta",
                "items": [
                    {"id": 20, "name": "Spaghetti", "description": "500g", "optional": False},
                    {"id": 21, "name": "Parmesan", "description": "", "optional": True},
                ],
            },
        )
    )
    route = respx.post(f"{BASE}/api/household/1/shoppinglist/2/recipeitems").mock(
        return_value=httpx.Response(200, json={"msg": "DONE"})
    )
    result = await mcp_client.call_tool(
        "add_recipe_items_to_shopping_list", {"list_id": 2, "recipe_id": 5}
    )
    assert json.loads(route.calls.last.request.content) == {
        "items": [{"id": 20, "description": "500g"}]
    }
    assert "1 ingredient(s)" in result.data
    assert "Pasta" in result.data


@respx.mock
async def test_404_becomes_actionable_tool_error(mcp_client):
    respx.get(f"{BASE}/api/household/1/shoppinglist/99/items").mock(
        return_value=httpx.Response(404, json={"msg": "Not found"})
    )
    with pytest.raises(ToolError, match="404"):
        await mcp_client.call_tool("get_shopping_list_items", {"list_id": 99})


@respx.mock
async def test_401_mentions_token_env_var(mcp_client):
    respx.get(f"{BASE}/api/household/1/shoppinglist").mock(
        return_value=httpx.Response(401, json={"msg": "Token has expired"})
    )
    with pytest.raises(ToolError, match="KITCHENOWL_TOKEN"):
        await mcp_client.call_tool("list_shopping_lists", {})
