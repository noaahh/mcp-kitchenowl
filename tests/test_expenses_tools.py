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
    assert payload["category"] == 3


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
                    "paid_by_id": 1,
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
            200, json=[{"id": 3, "name": "Food", "color": 0xFFF2C94C, "budget": 200}]
        )
    )
    result = await mcp_client.call_tool("get_expense_categories", {})
    assert result.data == [{"id": 3, "name": "Food", "color": "#F2C94C", "budget": 200}]


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


@respx.mock
async def test_add_expense_weighted_split(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/expense").mock(
        return_value=httpx.Response(200, json={"id": 9, "name": "Migros", "amount": 100})
    )
    await mcp_client.call_tool(
        "add_expense",
        {"name": "Migros", "amount": 100, "paid_by": 1, "paid_for": {"1": 60, "2": 40}},
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["paid_for"] == [{"id": 1, "factor": 60}, {"id": 2, "factor": 40}]


@respx.mock
async def test_create_expense_category_sends_color(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/expense/categories").mock(
        return_value=httpx.Response(200, json={"id": 4, "name": "Vorrat"})
    )
    result = await mcp_client.call_tool("create_expense_category", {"name": "Vorrat"})
    assert json.loads(route.calls.last.request.content) == {"name": "Vorrat", "color": None}
    assert result.data == {"id": 4, "name": "Vorrat", "color": None, "budget": None}


@respx.mock
async def test_create_expense_category_with_color_and_budget(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/expense/categories").mock(
        return_value=httpx.Response(200, json={"id": 4, "name": "Vorrat"})
    )
    await mcp_client.call_tool(
        "create_expense_category", {"name": "Vorrat", "color": "#A1887F", "budget": 100}
    )
    assert json.loads(route.calls.last.request.content) == {
        "name": "Vorrat",
        "color": 0xFFA1887F,
        "budget": 100,
    }


@respx.mock
async def test_update_expense_category(mcp_client):
    route = respx.post(f"{BASE}/api/expense/categories/4").mock(
        return_value=httpx.Response(
            200, json={"id": 4, "name": "Vorrat", "color": 0xFFA1887F, "budget": 100}
        )
    )
    result = await mcp_client.call_tool(
        "update_expense_category",
        {"category_id": 4, "color": "a1887f", "budget": 100, "merge_category_id": 7},
    )
    assert json.loads(route.calls.last.request.content) == {
        "color": 0xFFA1887F,
        "budget": 100,
        "merge_category_id": 7,
    }
    assert result.data["color"] == "#A1887F"


@respx.mock
async def test_delete_expense_category(mcp_client):
    route = respx.delete(f"{BASE}/api/expense/categories/4").mock(
        return_value=httpx.Response(200, json={"msg": "DONE"})
    )
    await mcp_client.call_tool("delete_expense_category", {"category_id": 4})
    assert route.called


@respx.mock
async def test_list_expenses_date_range_pages_through_ties(mcp_client):
    day = 1759276800000  # 2025-10-01
    first = [{"id": 100 - i, "date": day + 1000 * (30 - i)} for i in range(30)]
    # second page repeats the entry sharing the last timestamp, then one older entry
    second = [first[-1], {"id": 1, "date": day}]
    route = respx.get(f"{BASE}/api/household/1/expense").mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )
    result = await mcp_client.call_tool(
        "list_expenses", {"date_from": "2025-10-01", "date_to": "2025-10-31"}
    )
    assert len(result.data) == 31
    first_params = route.calls[0].request.url.params
    assert first_params["endBeforeDate"] == str(day - 1)
    assert first_params["startAfterDate"] == str(1761868800000 + 24 * 60 * 60 * 1000)
    assert route.calls[1].request.url.params["startAfterDate"] == str(first[-1]["date"] + 1)


@respx.mock
async def test_add_expense_excluded_from_statistics(mcp_client):
    route = respx.post(f"{BASE}/api/household/1/expense").mock(
        return_value=httpx.Response(200, json={"id": 9, "exclude_from_statistics": True})
    )
    result = await mcp_client.call_tool(
        "add_expense",
        {"name": "Springform", "amount": 13.95, "paid_by": 1, "paid_for": [1],
         "exclude_from_statistics": True},
    )
    assert json.loads(route.calls.last.request.content)["exclude_from_statistics"] is True
    assert result.data["exclude_from_statistics"] is True


@respx.mock
async def test_expense_overview_params(mcp_client):
    route = respx.get(f"{BASE}/api/household/1/expense/overview").mock(
        return_value=httpx.Response(200, json={})
    )
    await mcp_client.call_tool(
        "get_expense_overview", {"frame": "yearly", "steps": 2, "personal": True}
    )
    assert dict(route.calls.last.request.url.params) == {
        "frame": "3", "steps": "2", "page": "0", "view": "1"
    }
