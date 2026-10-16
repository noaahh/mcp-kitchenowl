import json

import httpx
import respx

from tests.conftest import BASE

RECIPE = {
    "id": 5,
    "name": "Pasta",
    "description": "Cook it.",
    "time": 30,
    "cook_time": 20,
    "prep_time": 10,
    "yields": 4,
    "source": "https://example.com",
    "photo": "huge-base64-blob",
    "photo_hash": "abc",
    "tags": [{"id": 1, "name": "italian"}],
    "items": [{"id": 20, "name": "Spaghetti", "description": "500g", "optional": False}],
}


@respx.mock
async def test_get_recipe_slims_and_strips_photo(mcp_client):
    respx.get(f"{BASE}/api/recipe/5").mock(
        return_value=httpx.Response(200, json=RECIPE)
    )
    result = await mcp_client.call_tool("get_recipe", {"recipe_id": 5})
    assert result.data["name"] == "Pasta"
    assert result.data["tags"] == ["italian"]
    assert result.data["items"] == [
        {"id": 20, "name": "Spaghetti", "description": "500g", "optional": False}
    ]
    assert "photo" not in result.data


@respx.mock
async def test_list_recipes_summary(mcp_client):
    respx.get(f"{BASE}/api/household/1/recipe").mock(
        return_value=httpx.Response(200, json=[RECIPE])
    )
    result = await mcp_client.call_tool("list_recipes", {})
    assert result.data == [
        {"id": 5, "name": "Pasta", "time": 30, "yields": 4, "tags": ["italian"]}
    ]


@respx.mock
async def test_create_recipe_payload(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/recipe").mock(
        return_value=httpx.Response(200, json=RECIPE)
    )
    await mcp_client.call_tool(
        "create_recipe",
        {
            "name": "Pasta",
            "description": "Cook it.",
            "time": 30,
            "items": [{"name": "Spaghetti", "description": "500g"}],
            "tags": ["italian"],
        },
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["name"] == "Pasta"
    assert payload["items"] == [{"name": "Spaghetti", "description": "500g", "optional": False}]
    assert payload["tags"] == ["italian"]


@respx.mock
async def test_import_recipe_from_url_draft_only(mcp_client):
    respx.get(f"{BASE}/api/household/1/recipe/scrape").mock(
        return_value=httpx.Response(200, json={"recipe": RECIPE})
    )
    result = await mcp_client.call_tool(
        "import_recipe_from_url", {"url": "https://example.com/pasta"}
    )
    assert result.data["saved"] is False
    assert result.data["draft"]["name"] == "Pasta"


@respx.mock
async def test_import_recipe_from_url_falls_back_to_post(mcp_client):
    respx.get(f"{BASE}/api/household/1/recipe/scrape").mock(
        return_value=httpx.Response(405, text="Method Not Allowed")
    )
    respx.post(f"{BASE}/api/household/1/recipe/scrape").mock(
        return_value=httpx.Response(200, json={"recipe": RECIPE})
    )
    save_route = respx.post(f"{BASE}/api/household/1/recipe").mock(
        return_value=httpx.Response(200, json=RECIPE)
    )
    result = await mcp_client.call_tool(
        "import_recipe_from_url", {"url": "https://example.com/pasta", "save": True}
    )
    assert result.data["saved"] is True
    assert save_route.called


@respx.mock
async def test_list_tags(mcp_client):
    respx.get(f"{BASE}/api/household/1/tag").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "Dessert"}, {"id": 2, "name": "Backen"}])
    )
    result = await mcp_client.call_tool("list_tags", {})
    assert result.data == ["Dessert", "Backen"]
