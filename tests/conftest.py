import pytest
from fastmcp import Client

from kitchenowl_mcp.client import KitchenOwlClient
from kitchenowl_mcp.server import create_server
from kitchenowl_mcp.tools import set_client

BASE = "https://kitchenowl.test"


@pytest.fixture
async def mcp_client():
    """In-memory MCP client against the real server, with a single-household KitchenOwl client.

    Tests mock the KitchenOwl REST API with respx; household resolution is pinned to id 1.
    """
    ko_client = KitchenOwlClient(BASE, "test-token", default_household_id=1)
    set_client(ko_client)
    server = create_server(with_lifespan=False)
    try:
        async with Client(server) as client:
            yield client
    finally:
        set_client(None)
        await ko_client.aclose()
