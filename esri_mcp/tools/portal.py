"""Portal item search and details (ArcGIS Online or Enterprise portal)."""

import os
from datetime import UTC, datetime

from esri_mcp.client import EsriClient
from esri_mcp.models import PortalItem, PortalSearchResult

AGOL_PORTAL = "https://www.arcgis.com"


def _portal_base() -> str:
    return (os.environ.get("ARCGIS_PORTAL_URL") or AGOL_PORTAL).rstrip("/")


def _item_from_json(item: dict) -> PortalItem:
    modified = item.get("modified")
    return PortalItem(
        id=item["id"],
        title=item.get("title", ""),
        type=item.get("type", ""),
        owner=item.get("owner"),
        snippet=item.get("snippet") or None,
        url=item.get("url") or None,
        modified=(
            datetime.fromtimestamp(modified / 1000.0, tz=UTC).isoformat() if modified else None
        ),
        tags=item.get("tags") or [],
    )


async def search_portal_items(
    client: EsriClient,
    query: str,
    item_type: str | None = None,
    max_results: int = 10,
) -> PortalSearchResult:
    q = query
    if item_type:
        q = f'{q} AND type:"{item_type}"'
    url = f"{_portal_base()}/sharing/rest/search"
    body = await client.get_json(url, {"q": q, "num": max_results})
    items = [_item_from_json(i) for i in body.get("results", [])]
    return PortalSearchResult(
        total=body.get("total", len(items)),
        count=len(items),
        items=items,
        source_url=url,
    )


async def get_item_details(client: EsriClient, item_id: str) -> PortalItem:
    url = f"{_portal_base()}/sharing/rest/content/items/{item_id}"
    body = await client.get_json(url)
    return _item_from_json(body)
