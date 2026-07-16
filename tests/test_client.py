import httpx
import pytest
import respx

from kitchenowl_mcp.client import KitchenOwlClient, KitchenOwlError

BASE = "https://kitchenowl.test"


@pytest.fixture
async def client():
    c = KitchenOwlClient(BASE + "/", "test-token")
    yield c
    await c.aclose()


@respx.mock
async def test_request_sends_bearer_and_joins_url(client):
    route = respx.get(f"{BASE}/api/household").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "Home"}])
    )
    result = await client.request("GET", "/household")
    assert result == [{"id": 1, "name": "Home"}]
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-token"


@respx.mock
async def test_error_mapping_uses_server_msg(client):
    respx.get(f"{BASE}/api/household").mock(
        return_value=httpx.Response(401, json={"msg": "Token has expired"})
    )
    with pytest.raises(KitchenOwlError) as exc_info:
        await client.request("GET", "/household")
    assert exc_info.value.status_code == 401
    assert "Token has expired" in exc_info.value.message


@respx.mock
async def test_error_mapping_without_json_body(client):
    respx.delete(f"{BASE}/api/household/1/shoppinglist/9").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(KitchenOwlError) as exc_info:
        await client.request("DELETE", "/household/1/shoppinglist/9")
    assert exc_info.value.status_code == 500
    assert "boom" in exc_info.value.message


@respx.mock
async def test_connect_error_is_wrapped(client):
    respx.get(f"{BASE}/api/household").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(KitchenOwlError) as exc_info:
        await client.request("GET", "/household")
    assert exc_info.value.status_code is None
    assert "Cannot reach KitchenOwl" in exc_info.value.message


@respx.mock
async def test_empty_response_returns_none(client):
    respx.delete(f"{BASE}/api/household/1/shoppinglist/9").mock(
        return_value=httpx.Response(204)
    )
    assert await client.request("DELETE", "/household/1/shoppinglist/9") is None


async def test_resolve_household_explicit_arg(client):
    assert await client.resolve_household(7) == 7


async def test_resolve_household_configured_default():
    c = KitchenOwlClient(BASE, "t", default_household_id=3)
    assert await c.resolve_household() == 3
    await c.aclose()


@respx.mock
async def test_resolve_household_auto_pick_single(client):
    respx.get(f"{BASE}/api/household").mock(
        return_value=httpx.Response(200, json=[{"id": 5, "name": "Home"}])
    )
    assert await client.resolve_household() == 5
    # cached: no second request needed
    respx.reset()
    assert await client.resolve_household() == 5


@respx.mock
async def test_resolve_household_multiple_raises(client):
    respx.get(f"{BASE}/api/household").mock(
        return_value=httpx.Response(
            200, json=[{"id": 1, "name": "Home"}, {"id": 2, "name": "Cabin"}]
        )
    )
    with pytest.raises(KitchenOwlError) as exc_info:
        await client.resolve_household()
    assert "Home (id=1)" in exc_info.value.message
    assert "KITCHENOWL_HOUSEHOLD_ID" in exc_info.value.message
