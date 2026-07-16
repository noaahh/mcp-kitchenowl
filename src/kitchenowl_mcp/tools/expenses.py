"""Expense tools."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastmcp import FastMCP

from kitchenowl_mcp.tools import get_client, kitchenowl_tool


def _iso_date_to_epoch_ms(value: str) -> int:
    parsed = date.fromisoformat(value)
    return int(datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC).timestamp() * 1000)


def _slim_expense(expense: dict[str, Any]) -> dict[str, Any]:
    category = expense.get("category")
    paid_by = expense.get("paid_by")
    return {
        "id": expense.get("id"),
        "name": expense.get("name"),
        "amount": expense.get("amount"),
        "date": expense.get("date"),
        "description": expense.get("description") or "",
        "category": category.get("name") if isinstance(category, dict) else category,
        "paid_by": paid_by.get("id") if isinstance(paid_by, dict) else paid_by,
        "paid_for": [
            {"user_id": pf.get("user_id", pf.get("id")), "factor": pf.get("factor")}
            for pf in expense.get("paid_for", []) or []
        ],
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @kitchenowl_tool
    async def list_expenses(
        search: str | None = None,
        household_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List the household's most recent expenses (newest first), optionally filtered by name."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        expenses = await client.request(
            "GET", f"/household/{hid}/expense", params=params or None
        )
        return [_slim_expense(e) for e in expenses]

    @mcp.tool
    @kitchenowl_tool
    async def add_expense(
        name: str,
        amount: float,
        paid_by: int,
        paid_for: list[int] | None = None,
        expense_date: str | None = None,
        category_id: int | None = None,
        description: str = "",
        household_id: int | None = None,
    ) -> dict[str, Any]:
        """Add an expense to the household.

        paid_by is the member's user id (see get_household). paid_for lists the user ids
        the expense is split between (equal split; defaults to all household members).
        expense_date is an ISO date (YYYY-MM-DD; defaults to now). Get category ids from
        get_expense_categories.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        if not paid_for:
            household = await client.request("GET", f"/household/{hid}")
            paid_for = [m["id"] for m in household.get("member", []) or []]
        payload: dict[str, Any] = {
            "name": name,
            "amount": amount,
            "paid_by": {"id": paid_by},
            "paid_for": [{"id": uid, "factor": 1} for uid in paid_for],
        }
        if description:
            payload["description"] = description
        if expense_date is not None:
            payload["date"] = _iso_date_to_epoch_ms(expense_date)
        if category_id is not None:
            payload["category"] = {"id": category_id}
        result = await client.request("POST", f"/household/{hid}/expense", json=payload)
        return _slim_expense(result) if isinstance(result, dict) else {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def update_expense(
        expense_id: int,
        name: str | None = None,
        amount: float | None = None,
        paid_by: int | None = None,
        paid_for: list[int] | None = None,
        expense_date: str | None = None,
        category_id: int | None = None,
        description: str | None = None,
        household_id: int | None = None,
    ) -> str:
        """Update an expense. Only the fields you pass are changed."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if amount is not None:
            payload["amount"] = amount
        if paid_by is not None:
            payload["paid_by"] = {"id": paid_by}
        if paid_for is not None:
            payload["paid_for"] = [{"id": uid, "factor": 1} for uid in paid_for]
        if expense_date is not None:
            payload["date"] = _iso_date_to_epoch_ms(expense_date)
        if category_id is not None:
            payload["category"] = {"id": category_id}
        if description is not None:
            payload["description"] = description
        if not payload:
            return "Nothing to update — pass at least one field."
        await client.request("POST", f"/household/{hid}/expense/{expense_id}", json=payload)
        return f"Expense {expense_id} updated."

    @mcp.tool
    @kitchenowl_tool
    async def delete_expense(expense_id: int, household_id: int | None = None) -> str:
        """Delete an expense. This cannot be undone."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request("DELETE", f"/household/{hid}/expense/{expense_id}")
        return f"Expense {expense_id} deleted."

    @mcp.tool
    @kitchenowl_tool
    async def get_expense_categories(household_id: int | None = None) -> list[dict[str, Any]]:
        """List the household's expense categories (ids usable in add_expense/update_expense)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        categories = await client.request("GET", f"/household/{hid}/expense/categories")
        return [
            {"id": c.get("id"), "name": c.get("name"), "budget": c.get("budget")}
            for c in categories
        ]

    @mcp.tool
    @kitchenowl_tool
    async def create_expense_category(
        name: str, household_id: int | None = None
    ) -> dict[str, Any]:
        """Create a new expense category."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        result = await client.request(
            "POST", f"/household/{hid}/expense/categories", json={"name": name}
        )
        if isinstance(result, dict):
            return {"id": result.get("id"), "name": result.get("name")}
        return {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def get_expense_overview(household_id: int | None = None) -> Any:
        """Get the household's expense overview (totals per member/category)."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        return await client.request("GET", f"/household/{hid}/expense/overview")
