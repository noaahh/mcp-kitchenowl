import json

import httpx
import respx

from tests.conftest import BASE

HOUSEHOLD = {
    "id": 1,
    "name": "Home",
    "member": [
        {"id": 1, "name": "Alice", "username": "alice", "admin": True},
        {"id": 2, "name": "Bob", "username": "bob", "admin": False},
    ],
}


@respx.mock
async def test_add_expense_defaults_split_to_all_members(mcp_client):
    respx.get(f"{BASE}/api/household/1").mock(return_value=httpx.Response(200, json=HOUSEHOLD))
    route = respx.post(f"{BASE}/api/household/1/expense").mock(
        return_value=httpx.Response(
            200,
            json={"id": 9, "name": "Groceries", "amount": 42.5, "paid_by": {"id": 1}},
        )
    )
    result = await mcp_client.call_tool(
        "add_expense", {"name": "Groceries", "amount": 42.5, "paid_by": 1}
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["paid_by"] == {"id": 1}
    assert payload["paid_for"] == [{"id": 1, "factor": 1}, {"id": 2, "factor": 1}]
    assert result.data["id"] == 9


@respx.mock
async def test_add_expense_with_explicit_split_and_date(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/expense").mock(
        return_value=httpx.Response(200, json={"id": 9, "name": "Rent", "amount": 100})
    )
    await mcp_client.call_tool(
        "add_expense",
        {
            "name": "Rent",
            "amount": 100,
            "paid_by": 2,
            "paid_for": [2],
            "expense_date": "2025-07-01",
            "category_id": 3,
        },
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["paid_for"] == [{"id": 2, "factor": 1}]
    assert payload["date"] == 1751328000000
    assert payload["category"] == {"id": 3}


@respx.mock
async def test_list_expenses_slims(mcp_client):
    respx.get(f"{BASE}/api/household/1/expense").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 9,
                    "name": "Groceries",
                    "amount": 42.5,
                    "date": 1751328000000,
                    "category": {"id": 3, "name": "Food"},
                    "paid_by": {"id": 1, "name": "Alice"},
                    "paid_for": [{"user_id": 1, "factor": 1}],
                    "photo": "blob",
                }
            ],
        )
    )
    result = await mcp_client.call_tool("list_expenses", {})
    assert result.data[0]["category"] == "Food"
    assert result.data[0]["paid_by"] == 1
    assert "photo" not in result.data[0]


@respx.mock
async def test_get_expense_categories(mcp_client):
    respx.get(f"{BASE}/api/household/1/expense/categories").mock(
        return_value=httpx.Response(
            200, json=[{"id": 3, "name": "Food", "color": 5, "budget": 200}]
        )
    )
    result = await mcp_client.call_tool("get_expense_categories", {})
    assert result.data == [{"id": 3, "name": "Food", "budget": 200}]


@respx.mock
async def test_households_tools(mcp_client):
    respx.get(f"{BASE}/api/household").mock(
        return_value=httpx.Response(200, json=[HOUSEHOLD])
    )
    result = await mcp_client.call_tool("list_households", {})
    assert result.data == [{"id": 1, "name": "Home", "member_count": 2}]

    respx.get(f"{BASE}/api/household/1").mock(return_value=httpx.Response(200, json=HOUSEHOLD))
    result = await mcp_client.call_tool("get_household", {})
    assert [m["id"] for m in result.data["members"]] == [1, 2]
