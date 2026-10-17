"""Expense tools."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from fastmcp import FastMCP

from kitchenowl_mcp.tools import get_client, kitchenowl_tool


DAY_MS = 24 * 60 * 60 * 1000
# the backend returns expense lists in pages of this size
PAGE_SIZE = 30


def _iso_date_to_epoch_ms(value: str) -> int:
    parsed = date.fromisoformat(value)
    return int(datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC).timestamp() * 1000)


def _paid_for(paid_for: list[int] | dict[int, int]) -> list[dict[str, int]]:
    if isinstance(paid_for, dict):
        return [{"id": int(uid), "factor": factor} for uid, factor in paid_for.items()]
    return [{"id": uid, "factor": 1} for uid in paid_for]


def _color_to_int(color: str) -> int:
    # KitchenOwl stores Flutter ARGB ints; accept "#RRGGBB" and make it opaque
    digits = color.removeprefix("#")
    if len(digits) != 6:
        raise ValueError(f"color must be #RRGGBB, got {color!r}")
    return 0xFF000000 | int(digits, 16)


def _slim_category(category: dict[str, Any]) -> dict[str, Any]:
    color = category.get("color")
    return {
        "id": category.get("id"),
        "name": category.get("name"),
        "color": f"#{color & 0xFFFFFF:06X}" if isinstance(color, int) else None,
        "budget": category.get("budget"),
    }


def _slim_expense(expense: dict[str, Any]) -> dict[str, Any]:
    category = expense.get("category")
    # the API returns the paid_by_id column, not a paid_by object
    paid_by = expense.get("paid_by_id", expense.get("paid_by"))
    return {
        "id": expense.get("id"),
        "name": expense.get("name"),
        "amount": expense.get("amount"),
        "date": expense.get("date"),
        "description": expense.get("description") or "",
        "category": category.get("name") if isinstance(category, dict) else category,
        "exclude_from_statistics": bool(expense.get("exclude_from_statistics")),
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
        date_from: str | None = None,
        date_to: str | None = None,
        household_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List the household's expenses (newest first), optionally filtered by name.

        Without dates only the latest 30 are returned. With date_from and/or date_to
        (ISO dates, inclusive) every expense in that range is returned.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        # the backend filters date > endBeforeDate and date < startAfterDate
        if date_from:
            params["endBeforeDate"] = _iso_date_to_epoch_ms(date_from) - 1
        if date_to:
            params["startAfterDate"] = _iso_date_to_epoch_ms(date_to) + DAY_MS
        path = f"/household/{hid}/expense"
        expenses = await client.request("GET", path, params=params or None)
        if date_from or date_to:
            seen = {e["id"] for e in expenses}
            batch = expenses
            while len(batch) == PAGE_SIZE:
                # +1 keeps entries sharing the last timestamp; seen drops the repeats
                params["startAfterDate"] = batch[-1]["date"] + 1
                batch = await client.request("GET", path, params=params)
                new = [e for e in batch if e["id"] not in seen]
                # ponytail: more than PAGE_SIZE expenses on one timestamp stop paging here
                if not new:
                    break
                seen.update(e["id"] for e in new)
                expenses += new
        return [_slim_expense(e) for e in expenses]

    @mcp.tool
    @kitchenowl_tool
    async def add_expense(
        name: str,
        amount: float,
        paid_by: int,
        paid_for: list[int] | dict[int, int] | None = None,
        expense_date: str | None = None,
        category_id: int | None = None,
        description: str = "",
        exclude_from_statistics: bool = False,
        household_id: int | None = None,
    ) -> dict[str, Any]:
        """Add an expense to the household.

        paid_by is the member's user id (see get_household). paid_for is either a list of
        user ids (equal split; defaults to all household members) or a mapping of user id
        to integer share weight, e.g. {"1": 60, "2": 40} for a 60/40 split.
        expense_date is an ISO date (YYYY-MM-DD; defaults to now). Get category ids from
        get_expense_categories. Set exclude_from_statistics for one-off purchases that
        should not count in the overview (they still count in balances).
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
            "paid_for": _paid_for(paid_for),
        }
        if description:
            payload["description"] = description
        if exclude_from_statistics:
            payload["exclude_from_statistics"] = True
        if expense_date is not None:
            payload["date"] = _iso_date_to_epoch_ms(expense_date)
        if category_id is not None:
            payload["category"] = category_id
        result = await client.request("POST", f"/household/{hid}/expense", json=payload)
        return _slim_expense(result) if isinstance(result, dict) else {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def update_expense(
        expense_id: int,
        name: str | None = None,
        amount: float | None = None,
        paid_by: int | None = None,
        paid_for: list[int] | dict[int, int] | None = None,
        expense_date: str | None = None,
        category_id: int | None = None,
        description: str | None = None,
        exclude_from_statistics: bool | None = None,
        household_id: int | None = None,
    ) -> str:
        """Update an expense. Only the fields you pass are changed.

        paid_for takes the same forms as in add_expense.
        """
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
            payload["paid_for"] = _paid_for(paid_for)
        if expense_date is not None:
            payload["date"] = _iso_date_to_epoch_ms(expense_date)
        if category_id is not None:
            payload["category"] = category_id
        if description is not None:
            payload["description"] = description
        if exclude_from_statistics is not None:
            payload["exclude_from_statistics"] = exclude_from_statistics
        if not payload:
            return "Nothing to update — pass at least one field."
        await client.request("POST", f"/expense/{expense_id}", json=payload)
        return f"Expense {expense_id} updated."

    @mcp.tool
    @kitchenowl_tool
    async def delete_expense(expense_id: int, household_id: int | None = None) -> str:
        """Delete an expense. This cannot be undone."""
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request("DELETE", f"/expense/{expense_id}")
        return f"Expense {expense_id} deleted."

    @mcp.tool
    @kitchenowl_tool
    async def get_expense_categories(household_id: int | None = None) -> list[dict[str, Any]]:
        """List the household's expense categories with color (#RRGGBB) and monthly budget.

        The ids are usable in add_expense/update_expense.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        categories = await client.request("GET", f"/household/{hid}/expense/categories")
        return [_slim_category(c) for c in categories]

    @mcp.tool
    @kitchenowl_tool
    async def create_expense_category(
        name: str,
        color: str | None = None,
        budget: float | None = None,
        household_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new expense category.

        color is a hex color like "#F2C94C"; budget is the monthly budget amount.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        # the backend reads color unconditionally, so it is always sent
        payload: dict[str, Any] = {
            "name": name,
            "color": _color_to_int(color) if color else None,
        }
        if budget is not None:
            payload["budget"] = budget
        result = await client.request(
            "POST", f"/household/{hid}/expense/categories", json=payload
        )
        return _slim_category(result) if isinstance(result, dict) else {"name": name}

    @mcp.tool
    @kitchenowl_tool
    async def update_expense_category(
        category_id: int,
        name: str | None = None,
        color: str | None = None,
        budget: float | None = None,
        merge_category_id: int | None = None,
        household_id: int | None = None,
    ) -> dict[str, Any] | str:
        """Update an expense category. Only the fields you pass are changed.

        color is a hex color like "#F2C94C"; budget is the monthly budget amount.
        merge_category_id moves all expenses of that other category into this one and
        deletes the other category (use it to clean up duplicates).
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if color is not None:
            payload["color"] = _color_to_int(color)
        if budget is not None:
            payload["budget"] = budget
        if merge_category_id is not None:
            payload["merge_category_id"] = merge_category_id
        if not payload:
            return "Nothing to update — pass at least one field."
        result = await client.request(
            "POST", f"/expense/categories/{category_id}", json=payload
        )
        return _slim_category(result) if isinstance(result, dict) else f"Category {category_id} updated."

    @mcp.tool
    @kitchenowl_tool
    async def delete_expense_category(
        category_id: int, household_id: int | None = None
    ) -> str:
        """Delete an expense category. Its expenses stay, without a category.

        To keep the expenses categorized, merge it into another category instead
        (update_expense_category with merge_category_id).
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        await client.request("DELETE", f"/expense/categories/{category_id}")
        return f"Category {category_id} deleted."

    @mcp.tool
    @kitchenowl_tool
    async def get_expense_overview(
        frame: Literal["daily", "weekly", "monthly", "yearly"] = "monthly",
        steps: int = 5,
        page: int = 0,
        personal: bool = False,
        household_id: int | None = None,
    ) -> Any:
        """Get expense totals per category for the last `steps` frames (current first).

        page shifts the window back in time by `steps` frames. personal=true shows only
        your share instead of the household's. Expenses excluded from statistics are
        not counted.
        """
        client = get_client()
        hid = await client.resolve_household(household_id)
        params = {
            "frame": ["daily", "weekly", "monthly", "yearly"].index(frame),
            "steps": steps,
            "page": page,
            "view": int(personal),
        }
        return await client.request("GET", f"/household/{hid}/expense/overview", params=params)
