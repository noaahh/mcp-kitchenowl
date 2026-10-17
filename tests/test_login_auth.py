import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import httpx
import respx

from kitchenowl_mcp.auth import KitchenOwlOAuthProvider
from kitchenowl_mcp.server import create_server
from kitchenowl_mcp.tools import close_user_clients, set_kitchenowl_url

BASE = "https://kitchenowl.test"
MCP = "https://mcp.test"


def _sse_json(resp: httpx.Response) -> dict:
    lines = [line[5:] for line in resp.text.splitlines() if line.startswith("data:")]
    return json.loads(lines[-1]) if lines else resp.json()


@respx.mock
async def test_login_flow_calls_tools_as_the_logged_in_user(tmp_path):
    respx.post(f"{BASE}/api/auth").mock(
        return_value=httpx.Response(200, json={"access_token": "short", "refresh_token": "r"})
    )
    llt = respx.post(f"{BASE}/api/auth/llt").mock(
        return_value=httpx.Response(200, json={"longlived_token": "juliette-llt"})
    )
    households = respx.get(f"{BASE}/api/household").mock(
        return_value=httpx.Response(200, json=[{"id": 7, "name": "Home"}])
    )

    provider = KitchenOwlOAuthProvider(
        base_url=MCP, kitchenowl_url=BASE, secret_key="test-secret", data_dir=str(tmp_path)
    )
    set_kitchenowl_url(BASE)
    app = create_server(with_lifespan=False, auth=provider).http_app()
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    redirect = "https://claude.ai/api/mcp/auth_callback"

    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=MCP
    ) as http:
        assert (await http.post("/mcp", json={})).status_code == 401

        reg = (await http.post("/register", json={"redirect_uris": [redirect]})).json()
        auth = await http.get(
            "/authorize",
            params={
                "client_id": reg["client_id"],
                "redirect_uri": redirect,
                "response_type": "code",
                "state": "xyz",
                "code_challenge": challenge.decode(),
                "code_challenge_method": "S256",
            },
        )
        login_url = urlparse(auth.headers["location"])
        req = parse_qs(login_url.query)["req"][0]
        assert (await http.get(login_url.path, params={"req": req})).status_code == 200

        bad = await http.post("/login", data={"req": req})
        assert bad.status_code == 401

        done = await http.post("/login", data={"req": req, "username": "j", "password": "pw"})
        callback = parse_qs(urlparse(done.headers["location"]).query)
        assert callback["state"] == ["xyz"]
        assert json.loads(llt.calls[0].request.content) == {"device": "Claude MCP"}

        token = (
            await http.post(
                "/token",
                data={
                    "grant_type": "authorization_code",
                    "code": callback["code"][0],
                    "redirect_uri": redirect,
                    "client_id": reg["client_id"],
                    "client_secret": reg.get("client_secret", ""),
                    "code_verifier": verifier,
                },
            )
        ).json()
        assert "access_token" in token, token

        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/json, text/event-stream",
        }
        init = await http.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            },
        )
        headers["mcp-session-id"] = init.headers["mcp-session-id"]
        await http.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        result = _sse_json(
            await http.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "list_households", "arguments": {}},
                },
            )
        )

    await close_user_clients()
    assert "Home" in json.dumps(result)
    assert households.calls[0].request.headers["authorization"] == "Bearer juliette-llt"
