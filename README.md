# esri-mcp

An [MCP](https://modelcontextprotocol.io/) server that exposes ArcGIS data and services — both **ArcGIS Online** and **ArcGIS Enterprise** — as tools for LLM agents.

Point an agent at any ArcGIS REST endpoint and it can discover layers, inspect schemas, run attribute and spatial queries, geocode addresses, and search portal content. Built on raw ArcGIS REST via `httpx` (no 500 MB `arcgis` package dependency), with [FastMCP](https://github.com/modelcontextprotocol/python-sdk) over stdio.

**Read-only by design.** Write operations (`applyEdits`, delete, publish) are out of scope for v1.

## Tools

| Tool | What it does |
|---|---|
| `list_layers` | List all layers and tables on a MapServer/FeatureServer |
| `get_layer_info` | Layer metadata: real field names (not aliases), geometry type, record limits |
| `query_features` | SQL `where` + optional spatial filter; paginated, date-normalized, geometry off by default |
| `geocode_address` | Address/place → lon/lat candidates (AGOL World Geocoder) |
| `reverse_geocode` | Lon/lat → nearest street address |
| `search_portal_items` | Keyword search across ArcGIS Online or an Enterprise portal |
| `get_item_details` | Full details for one portal item by id |

### Designed for LLM consumption

Raw Esri JSON is verbose, inconsistent, and full of traps. This server normalizes at the boundary:

- **Esri errors actually raise.** Esri returns HTTP 200 with an `error` body; every response is checked and surfaced as a clean message (`"Layer 9 not found on service X — service has layers: 0, 1, 2"`), never an HTML page or raw traceback.
- **Context-window protection.** Queries default to `returnGeometry=false` and `outSR=4326`, paginate through `exceededTransferLimit`, cap at 5,000 records, and report `count` / `truncated` / `source_url` so the agent can cite and paginate. Requested geometry is simplified via `maxAllowableOffset`.
- **Dates are ISO 8601 strings**, not epoch milliseconds.
- **Real field names.** `get_layer_info` returns the queryable field name alongside its display alias — `where` clauses fail silently against aliases.
- **Long requests go as POST** automatically (IIS URL-length limits on Enterprise servers).
- **Geocoding stays transactional** (`forStorage=false`) to remain within free-tier terms.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12+ is fetched automatically).

```bash
git clone https://github.com/<you>/esri-mcp.git
cd esri-mcp
uv sync
uv run python -m esri_mcp     # starts the server on stdio
```

### Register with Claude Code

```bash
claude mcp add esri -- uv run --directory /path/to/esri-mcp python -m esri_mcp
```

### Debug interactively

```bash
npx @modelcontextprotocol/inspector uv run python -m esri_mcp
```

### Try it

No credentials needed for public services. Ask your agent something like:

> List the layers on `https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer`, then show me the five most populous states.

## Authentication

Anonymous access works out of the box — most public services need no token. For secured content, set env vars for **one** of three modes (checked in this order; see [.env.example](.env.example)):

| Mode | Env vars | Use for |
|---|---|---|
| IWA / NTLM | `ARCGIS_USE_NTLM=true`, `ARCGIS_USERNAME`, `ARCGIS_PASSWORD` | ArcGIS Server behind Integrated Windows Authentication (web-tier auth, no tokens). Username as `DOMAIN\user` or `user@domain`. Requires the optional extra: `uv sync --extra iwa` |
| API key | `ARCGIS_API_KEY` | ArcGIS Online API keys |
| OAuth2 | `ARCGIS_CLIENT_ID`, `ARCGIS_CLIENT_SECRET` | AGOL app registration (client_credentials) |
| Legacy token | `ARCGIS_USERNAME`, `ARCGIS_PASSWORD`, `ARCGIS_PORTAL_URL` | On-prem ArcGIS Enterprise (`generateToken`) |
| Standalone server token | `ARCGIS_USERNAME`, `ARCGIS_PASSWORD`, `ARCGIS_TOKEN_URL` | **Standalone ArcGIS Server** (no Portal) — point `ARCGIS_TOKEN_URL` at `https://server:6443/arcgis/tokens/generateToken` |

Tokens are cached in-process and refreshed 5 minutes before expiry. If a stale token hits a public endpoint, the request falls back to anonymous instead of failing. Setting `ARCGIS_PORTAL_URL` also points `search_portal_items` / `get_item_details` at your Enterprise portal instead of arcgis.com.

Credentials never appear in logs, error messages, or tool output.

### Custom geocoder

Geocoding defaults to the AGOL World Geocoder, but `ARCGIS_GEOCODER_URL` points both geocoding tools at any ArcGIS `GeocodeServer` — an Enterprise locator, a standalone-server locator, or a custom-built one:

```
ARCGIS_GEOCODER_URL=https://your-server.example.com/arcgis/rest/services/YourLocator/GeocodeServer
```

### Standalone ArcGIS Server (no Portal)

The layer/query tools take full service URLs, so they work against any ArcGIS Server REST endpoint — federated or standalone, public or secured. For a secured standalone server, use `ARCGIS_TOKEN_URL` (token auth) or `ARCGIS_USE_NTLM` (IWA). The portal tools (`search_portal_items`, `get_item_details`) don't apply to standalone servers — discover services via the REST services directory instead.

## Development

```bash
uv sync                                   # install deps (incl. dev group)
uv run pytest -q -m "not integration"     # offline unit tests (mock transport + recorded JSON)
uv run pytest -q -m integration           # live tests against sampleserver6.arcgisonline.com
uv run pytest -q                          # everything
uv run ruff check . && uv run ruff format --check .   # lint + format check
```

Every Esri REST gotcha has a regression test: error-in-200 bodies, HTML-instead-of-JSON responses, pagination stitching, truncation flagging, epoch-date conversion, alias-vs-field-name, POST-for-long-queries, and anonymous fallback.

### Layout

```
esri_mcp/
  server.py          # FastMCP app, tool registration, transport (stdio; one-line swap to HTTP)
  auth.py            # token acquisition + caching (API key / OAuth2 / generateToken / anonymous)
  client.py          # httpx wrapper: retries, f=json, error normalization, POST fallback
  models.py          # Pydantic request/response models
  tools/
    layers.py        # discovery + metadata
    query.py         # feature queries: pagination, date conversion, record caps
    geocode.py       # geocode / reverse geocode (AGOL World Geocoder)
    portal.py        # item search, item details
tests/               # unit tests (offline) + live integration tests (marked)
```

## Roadmap

- `streamable-http` transport for hosted use (n8n, Hermes) — already a one-line swap in `server.py`
- Write operations behind an explicit `ESRI_MCP_ALLOW_WRITES=true` gate

## License

MIT
