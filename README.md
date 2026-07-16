# kitchenowl-mcp

An [MCP](https://modelcontextprotocol.io) server for [KitchenOwl](https://github.com/TomBursch/kitchenowl), built with [FastMCP](https://gofastmcp.com). It lets AI assistants (Claude, or any MCP client) manage your shopping lists, recipes, meal plan, and shared expenses over KitchenOwl's REST API.

It runs as a standalone service with streamable HTTP transport — typically as a Docker container next to your KitchenOwl instance. It is independent of KitchenOwl's built-in `/api/mcp` endpoint and also works with older KitchenOwl servers.

## Quick start (Docker Compose)

```bash
cp .env.example .env      # fill in KITCHENOWL_TOKEN (and JWT_SECRET_KEY for the bundled KitchenOwl)
docker compose up -d
```

The MCP endpoint is then available at `http://localhost:8000/mcp`.

If you already run KitchenOwl elsewhere, only build/run the `kitchenowl-mcp` service and point `KITCHENOWL_URL` at your instance.

### Configuration

| Env var | Required | Default | Description |
|---|---|---|---|
| `KITCHENOWL_URL` | yes | — | Base URL of your KitchenOwl instance (no trailing `/api`) |
| `KITCHENOWL_TOKEN` | yes | — | Long-lived token of the KitchenOwl user to act as |
| `KITCHENOWL_HOUSEHOLD_ID` | no | auto | Default household; auto-picked when the user has exactly one |
| `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | no | `0.0.0.0` / `8000` / `/mcp` | Where the MCP HTTP endpoint listens |
| `MCP_SERVER_TOKEN` | no | unset | If set, MCP clients must send `Authorization: Bearer <token>` |

### Getting a long-lived token

In the KitchenOwl app: **Profile → Sessions → create a long-lived token**, or via the API:

```bash
# 1. Log in (returns a short-lived access_token)
curl -X POST "$KITCHENOWL_URL/api/auth" -H 'Content-Type: application/json' \
     -d '{"username":"you","password":"your-password"}'

# 2. Mint a long-lived token with it
curl -X POST "$KITCHENOWL_URL/api/auth/llt" \
     -H "Authorization: Bearer <access_token>" \
     -H 'Content-Type: application/json' -d '{"device":"kitchenowl-mcp"}'
```

## Connecting a client

- **Claude Code**: `claude mcp add --transport http kitchenowl http://localhost:8000/mcp`
- **Claude Desktop / claude.ai custom connector**: add a remote MCP server with the URL `https://<your-host>/mcp` (must be HTTPS-reachable; put a reverse proxy in front)
- **MCP Inspector**: `npx @modelcontextprotocol/inspector`, connect to `http://localhost:8000/mcp` (streamable HTTP)

If `MCP_SERVER_TOKEN` is set, configure the client to send it as a bearer token.

## Tools

All household-scoped tools take an optional `household_id`; with a single household (or `KITCHENOWL_HOUSEHOLD_ID` set) it can be omitted.

**Households** — `list_households`, `get_household` (includes member ids for expenses)

**Shopping lists** — `list_shopping_lists`, `create_shopping_list`, `rename_shopping_list`, `delete_shopping_list`, `get_shopping_list_items`, `add_shopping_list_item`, `update_shopping_list_item`, `remove_shopping_list_items` (batch), `get_recent_items`, `get_suggested_items`, `add_recipe_items_to_shopping_list`, `search_items`, `update_item`

> KitchenOwl has no check/uncheck state: **removing an item means it was purchased** and feeds the purchase history and suggestions.

**Recipes** — `list_recipes`, `search_recipes`, `get_recipe`, `create_recipe`, `update_recipe`, `delete_recipe`, `import_recipe_from_url` (scrapes a recipe website; returns a draft unless `save=true`)

**Meal planner** — `get_meal_plan`, `add_recipe_to_plan`, `remove_recipe_from_plan`, `get_recipe_suggestions`

**Expenses** — `list_expenses`, `add_expense`, `update_expense`, `delete_expense`, `get_expense_categories`, `create_expense_category`, `get_expense_overview`

## Security

By default the MCP endpoint is **unauthenticated** — anyone who can reach it acts as the configured KitchenOwl user. Options, in increasing order of robustness:

1. Keep the port on a trusted network (Docker-internal, LAN, VPN).
2. Set `MCP_SERVER_TOKEN` to require a bearer token (static token — fine for personal use, not a full auth system).
3. Put a reverse proxy (Caddy/Traefik/nginx) with TLS in front — required anyway for claude.ai remote connectors.

## Development

```bash
uv sync                                   # install deps (Python >= 3.11)
uv run pytest                             # run the test suite (mocked KitchenOwl API)
uv run ruff check .                       # lint
KITCHENOWL_URL=... KITCHENOWL_TOKEN=... uv run kitchenowl-mcp   # run locally
```

The tests use FastMCP's in-memory client with a [respx](https://lundberg.github.io/respx/)-mocked KitchenOwl API, so no running KitchenOwl instance is needed.

## Limitations / roadmap

- No item-catalog create/delete tools (`add_shopping_list_item` creates catalog items implicitly).
- No household create/delete or member management.
- Recipe `update_recipe` with `items`/`tags` replaces the full list (KitchenOwl API semantics).
- KitchenOwl's own experimental MCP endpoint (`/api/mcp`, recent versions) is an alternative if you don't need a separately deployable server.
