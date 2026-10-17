"""OAuth for remote MCP clients (e.g. claude.ai) that logs users in with their KitchenOwl account.

The login page trades the user's KitchenOwl credentials for a long-lived KitchenOwl token.
Authorization codes and MCP tokens are Fernet-encrypted blobs carrying that token, so the
server keeps no token state and survives restarts. Only client registrations hit disk.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastmcp.server.auth.auth import AccessToken, ClientRegistrationOptions, OAuthProvider
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

LOGIN_REQUEST_TTL = 15 * 60
AUTH_CODE_TTL = 5 * 60
ACCESS_TOKEN_TTL = 30 * 24 * 3600


class KitchenOwlOAuthProvider(OAuthProvider):
    def __init__(self, *, base_url: str, kitchenowl_url: str, secret_key: str, data_dir: str):
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self._kitchenowl_api = kitchenowl_url.rstrip("/") + "/api"
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest()))
        self._clients_file = Path(data_dir) / "clients.json"

    # --- sealed blobs -------------------------------------------------------------

    def _seal(self, kind: str, data: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps({**data, "kind": kind}).encode()).decode()

    def _open(self, kind: str, blob: str, ttl: int | None) -> dict[str, Any] | None:
        try:
            data = json.loads(self._fernet.decrypt(blob.encode(), ttl=ttl))
        except (InvalidToken, ValueError):
            return None
        return data if data.get("kind") == kind else None

    # --- clients ------------------------------------------------------------------

    def _load_clients(self) -> dict[str, Any]:
        try:
            return json.loads(self._clients_file.read_text())
        except FileNotFoundError:
            return {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = self._load_clients().get(client_id)
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # ponytail: whole-file rewrite, fine for a handful of clients on one replica
        clients = self._load_clients()
        clients[client_info.client_id] = client_info.model_dump(mode="json", exclude_none=True)
        self._clients_file.parent.mkdir(parents=True, exist_ok=True)
        self._clients_file.write_text(json.dumps(clients))

    # --- authorization ------------------------------------------------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        req = self._seal(
            "login",
            {
                "client_id": client.client_id,
                "redirect_uri": str(params.redirect_uri),
                "explicit": params.redirect_uri_provided_explicitly,
                "state": params.state,
                "scopes": params.scopes or [],
                "challenge": params.code_challenge,
                "resource": params.resource,
            },
        )
        return f"{str(self.base_url).rstrip('/')}/login?req={req}"

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        return [*super().get_routes(mcp_path), Route("/login", self._login, methods=["GET", "POST"])]

    async def _login(self, request: Request) -> Response:
        form = await request.form() if request.method == "POST" else {}
        req = str(form.get("req") or request.query_params.get("req", ""))
        login = self._open("login", req, LOGIN_REQUEST_TTL)
        if login is None:
            return HTMLResponse(_page("This login link expired. Start again from Claude.", ""), 400)
        if request.method == "GET":
            return HTMLResponse(_page("", req))

        try:
            ko_token = await self._kitchenowl_token(
                str(form.get("username", "")).strip(),
                str(form.get("password", "")),
                str(form.get("token", "")).strip(),
            )
        except httpx.HTTPError:
            return HTMLResponse(_page("Could not reach KitchenOwl. Try again.", req), 502)
        if ko_token is None:
            return HTMLResponse(_page("Login failed. Check your credentials.", req), 401)

        # ponytail: stateless codes are replayable until expiry; PKCE still binds them to the client
        code = self._seal("code", {**login, "ko": ko_token})
        return RedirectResponse(
            construct_redirect_uri(login["redirect_uri"], code=code, state=login["state"]), 302
        )

    async def _kitchenowl_token(self, username: str, password: str, token: str) -> str | None:
        async with httpx.AsyncClient(base_url=self._kitchenowl_api, timeout=15) as http:
            if token:
                resp = await http.get("/user", headers={"Authorization": f"Bearer {token}"})
                return token if resp.status_code == 200 else None
            if not (username and password):
                return None
            resp = await http.post("/auth", json={"username": username, "password": password})
            if resp.status_code != 200:
                return None
            resp = await http.post(
                "/auth/llt",
                json={"device": "Claude MCP"},
                headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
            )
            return resp.json()["longlived_token"] if resp.status_code == 200 else None

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        data = self._open("code", authorization_code, AUTH_CODE_TTL)
        if data is None or data["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            client_id=data["client_id"],
            redirect_uri=data["redirect_uri"],
            redirect_uri_provided_explicitly=data["explicit"],
            scopes=data["scopes"],
            expires_at=time.time() + AUTH_CODE_TTL,
            code_challenge=data["challenge"],
            resource=data["resource"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        data = self._open("code", authorization_code.code, AUTH_CODE_TTL)
        if data is None:
            raise TokenError("invalid_grant", "Authorization code expired.")
        return self._issue(client.client_id, data["scopes"], data["ko"])

    # --- tokens -------------------------------------------------------------------

    def _issue(self, client_id: str, scopes: list[str], ko_token: str) -> OAuthToken:
        grant = {"client_id": client_id, "scopes": scopes, "ko": ko_token}
        return OAuthToken(
            access_token=self._seal("access", grant),
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=self._seal("refresh", grant),
            scope=" ".join(scopes) or None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        data = self._open("access", token, ACCESS_TOKEN_TTL)
        if data is None:
            return None
        return AccessToken(
            token=token,
            client_id=data["client_id"],
            scopes=data["scopes"],
            claims={"kitchenowl_token": data["ko"]},
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        data = self._open("refresh", refresh_token, None)
        if data is None or data["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=data["client_id"], scopes=data["scopes"])

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        data = self._open("refresh", refresh_token.token, None)
        if data is None:
            raise TokenError("invalid_grant", "Invalid refresh token.")
        return self._issue(client.client_id, scopes or data["scopes"], data["ko"])

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # ponytail: stateless tokens can't be revoked here; delete the "Claude MCP"
        # session in KitchenOwl (Profile -> Sessions) to cut access.
        return None


def _page(error: str, req: str) -> str:
    error_html = f'<p class="err">{html.escape(error)}</p>' if error else ""
    form = (
        f"""<form method="post">
  <input type="hidden" name="req" value="{html.escape(req)}">
  <label>Username or email<input name="username" autocomplete="username"></label>
  <label>Password<input name="password" type="password" autocomplete="current-password"></label>
  <details><summary>Use a long-lived token instead</summary>
    <label>Token (Profile &rarr; Sessions)<input name="token" autocomplete="off"></label>
  </details>
  <button>Connect</button>
</form>"""
        if req
        else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>KitchenOwl login</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:22rem;margin:4rem auto;padding:0 1rem;background:#fafafa;color:#222}}
@media (prefers-color-scheme:dark){{body{{background:#161616;color:#eee}}input{{background:#222;color:#eee;border-color:#444}}}}
label{{display:block;margin:.8rem 0}} input{{display:block;width:100%;box-sizing:border-box;padding:.5rem;margin-top:.25rem;border:1px solid #ccc;border-radius:6px}}
button{{margin-top:1rem;width:100%;padding:.6rem;border:0;border-radius:6px;background:#2e7d32;color:#fff;font-size:1rem}}
.err{{color:#c62828}} details{{margin:.8rem 0;font-size:.9rem}}
</style></head><body><h1>Connect KitchenOwl</h1>
<p>Sign in to let Claude use your KitchenOwl household.</p>{error_html}{form}</body></html>"""
