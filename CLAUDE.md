# CLAUDE.md — esri-mcp

MCP server exposing ArcGIS data and services (ArcGIS Online + ArcGIS Enterprise) as tools for LLM agents. Primary consumers: Claude Code (stdio) now, Hermes/n8n (HTTP) later.

## Prime directive

**Build over plan.** Ship a working tool, test it against a real service, then iterate. Do not produce roadmaps, phase plans, or architecture documents unless explicitly asked. When a decision is ambiguous, pick the simpler option, implement it, and note the alternative in a one-line comment.

## Stack decisions (settled — do not relitigate)

- **Python 3.12 + FastMCP** (`mcp` package, `FastMCP` class). Not TypeScript.
- **Raw ArcGIS REST via `httpx`** — do NOT add the `arcgis` (ArcGIS API for Python) package. It's a 500 MB+ dependency tree for what is ultimately `GET ...?f=json`. If a task genuinely needs it (e.g., publishing), stop and ask first.
- **`uv`** for env + dependency management. **`pytest`** for tests. **`ruff`** for lint/format.
- **Transport:** stdio by default. Keep all transport wiring in `server.py` so `mcp.run(transport="streamable-http")` is a one-line swap later.
- **Pydantic models** for tool inputs/outputs. Esri's raw JSON is verbose and inconsistent — normalize at the boundary, return clean shapes to the model.

## Project layout

```
esri_mcp/
  server.py          # FastMCP app, tool registration, transport
  auth.py            # token acquisition + caching (all flavors)
  client.py          # httpx wrapper: retries, f=json, error normalization
  tools/
    layers.py        # discovery + metadata
    query.py         # feature queries
    geocode.py       # geocode / reverse geocode
    portal.py        # item search, item details
  models.py          # Pydantic request/response models
tests/
  conftest.py        # fixtures hitting Esri's public sampleserver6 + recorded JSON
```

## Authentication

Support three modes, selected by which env vars are present (checked in this order):

1. `ARCGIS_API_KEY` — AGOL API key, passed as `token` param.
2. `ARCGIS_CLIENT_ID` / `ARCGIS_CLIENT_SECRET` — OAuth2 client_credentials against `https://www.arcgis.com/sharing/rest/oauth2/token`.
3. `ARCGIS_USERNAME` / `ARCGIS_PASSWORD` + `ARCGIS_PORTAL_URL` — legacy `generateToken` against `{portal}/sharing/rest/generateToken` (needed for on-prem Enterprise; `referer` param required).

Rules:
- Tokens are cached in-process with expiry tracking; refresh 5 minutes before `expires`.
- **Never** write tokens/keys to logs, error messages, code, or test fixtures. Env vars only (`.env` is gitignored; `.env.example` documents the names).
- Anonymous access must work — many public services need no token. Auth failure on a public endpoint should fall back to anonymous, not crash.

## Esri REST gotchas (read before touching client.py or query.py)

- Always append `f=json`. Esri returns HTML by default and **returns HTTP 200 for errors** — check for an `error` key in every JSON body and raise from it.
- **Pagination:** respect `maxRecordCount` (often 1000–2000). Loop with `resultOffset`/`resultRecordCount` while `exceededTransferLimit: true`. Cap total records per tool call (default 5000) and tell the model the result was truncated.
- **Token-context truncation:** a query tool that dumps 5000 features with full geometry will blow up the agent's context. Default `returnGeometry=false`; geometry only when explicitly requested, and simplify (`maxAllowableOffset`) or return centroid/extent summaries for large polygon sets.
- Date fields come back as **epoch milliseconds**. Convert to ISO 8601 strings in tool output.
- Field names: use `layer_info` to get real field names first; Esri aliases ≠ field names. (Remember the Sacramento permit feed lesson: `Parcel_No`, not `APN`.)
- Spatial reference: default `outSR=4326` for all tool output (LLM-readable lat/lon). Accept `inSR`/`outSR` overrides. Geometry params for spatial filters go as JSON in `geometry` + `geometryType` + `spatialRel`.
- `where=1=1` is the "all records" idiom. Always set `outFields` explicitly — `*` only when the user asks for everything.
- Geocoding: AGOL World Geocoder (`findAddressCandidates`, `reverseGeocode`) **requires a token for storage=true**; keep `forStorage=false` to stay within free/transactional terms.
- POST, not GET, when `where` clauses or geometry get long (URL length limits on Enterprise behind IIS).

## Tool design conventions

- Tool names: snake_case verbs — `list_layers`, `get_layer_info`, `query_features`, `geocode_address`, `reverse_geocode`, `search_portal_items`, `get_item_details`.
- Every tool docstring is written **for the LLM caller**: what it does, when to use it vs. siblings, one example invocation. This is the tool's prompt — treat it as such.
- Return structured dicts (via Pydantic `.model_dump()`), not prose. Include `count`, `truncated: bool`, and `source_url` in query results so the agent can cite/paginate.
- Errors return a clean message (`"Layer 3 not found on service X — service has layers 0–2"`), never raw tracebacks or Esri HTML.
- Destructive/write operations (applyEdits, delete, publish) are **out of scope for v1**. Read-only server. If added later, they require an explicit `ESRI_MCP_ALLOW_WRITES=true` env gate.

## Testing

- `tests/` runs against Esri's public sample servers (`sampleserver6.arcgisonline.com`) for integration, plus recorded JSON fixtures for unit tests so the suite passes offline.
- Every REST gotcha above gets a regression test (error-in-200 body, pagination loop, epoch dates).
- Run: `uv run pytest -q` (includes live tests). Offline: `uv run pytest -q -m "not integration"`. Lint: `uv run ruff check . && uv run ruff format --check .`

## Commands

```bash
uv sync                          # install deps
uv run python -m esri_mcp        # run server (stdio)
uv run pytest -q                 # tests
npx @modelcontextprotocol/inspector uv run python -m esri_mcp   # debug tools interactively
```

Claude Code registration (local dev):

```bash
claude mcp add esri -- uv run --directory /path/to/esri-mcp python -m esri_mcp
```

## Style

- Type hints everywhere; `ruff` defaults; line length 100.
- No speculative abstraction. One `client.py`, not a plugin system.
- Comments explain Esri weirdness, not Python syntax.
- Direct answers in commit messages and PR descriptions — no status nudges, no "next steps" sections.
