import json

import httpx
import respx

from tests.conftest import BASE


@respx.mock
async def test_get_meal_plan_converts_dates(mcp_client):
    respx.get(f"{BASE}/api/household/1/planner").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "recipe": {"id": 5, "name": "Pasta"},
                    "day": 2,
                    "cooking_date": 1752624000000,  # 2025-07-16 UTC
                    "yields": 4,
                }
            ],
        )
    )
    result = await mcp_client.call_tool("get_meal_plan", {})
    assert result.data == [
        {
            "recipe_id": 5,
            "recipe_name": "Pasta",
            "day": 2,
            "cooking_date": "2025-07-16",
            "yields": 4,
        }
    ]


@respx.mock
async def test_add_recipe_to_plan_iso_date_to_epoch_ms(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/planner/recipe").mock(
        return_value=httpx.Response(200, json={"msg": "DONE"})
    )
    await mcp_client.call_tool(
        "add_recipe_to_plan", {"recipe_id": 5, "cooking_date": "2025-07-16", "yields": 2}
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload == {"recipe_id": 5, "cooking_date": 1752624000000, "yields": 2}


@respx.mock
async def test_remove_recipe_from_plan(mcp_client):
    route = respx.delete(f"{BASE}/api/household/1/planner/recipe/5").mock(
        return_value=httpx.Response(200, json={"msg": "DONE"})
    )
    result = await mcp_client.call_tool("remove_recipe_from_plan", {"recipe_id": 5, "day": 2})
    assert json.loads(route.calls.last.request.content) == {"day": 2}
    assert "removed" in result.data


@respx.mock
async def test_get_recipe_suggestions_kinds(mcp_client):
    respx.get(f"{BASE}/api/household/1/planner/suggested-recipes").mock(
        return_value=httpx.Response(200, json=[{"id": 5, "name": "Pasta", "time": 30, "tags": []}])
    )
    result = await mcp_client.call_tool("get_recipe_suggestions", {})
    assert result.data == [{"id": 5, "name": "Pasta", "time": 30, "tags": []}]

    respx.get(f"{BASE}/api/household/1/planner/recent-recipes").mock(
        return_value=httpx.Response(200, json=[])
    )
    result = await mcp_client.call_tool("get_recipe_suggestions", {"kind": "recent"})
    assert result.data == []
