"""Thin async HTTP client for the KitchenOwl REST API."""

from __future__ import annotations

from typing import Any

import httpx


class KitchenOwlError(Exception):
    """Raised when KitchenOwl returns an error response or is unreachable."""

    def __init__(self, status_code: int | None, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _extract_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            for key in ("msg", "message", "error", "description"):
                if body.get(key):
                    return str(body[key])
    except ValueError:
        pass
    text = response.text.strip()
    return text[:200] if text else response.reason_phrase


class KitchenOwlClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        default_household_id: int | None = None,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._default_household_id = default_household_id
        self._http = httpx.AsyncClient(
            base_url=self.base_url + "/api",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self._http.request(method, path, json=json, params=params)
        except httpx.ConnectError as exc:
            raise KitchenOwlError(
                None, f"Cannot reach KitchenOwl at {self.base_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise KitchenOwlError(
                None, f"Request to KitchenOwl at {self.base_url} timed out: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise KitchenOwlError(response.status_code, _extract_message(response))
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def resolve_household(self, household_id: int | None = None) -> int:
        """Resolve the household to operate on: explicit arg > configured default > auto-pick."""
        if household_id is not None:
            return household_id
        if self._default_household_id is not None:
            return self._default_household_id
        households = await self.request("GET", "/household")
        if isinstance(households, list) and len(households) == 1:
            self._default_household_id = int(households[0]["id"])
            return self._default_household_id
        names = (
            ", ".join(f"{h['name']} (id={h['id']})" for h in households)
            if isinstance(households, list) and households
            else "none found"
        )
        raise KitchenOwlError(
            400,
            "Cannot determine which household to use. Available households: "
            f"{names}. Pass household_id explicitly or set KITCHENOWL_HOUSEHOLD_ID.",
        )

    async def aclose(self) -> None:
        await self._http.aclose()
