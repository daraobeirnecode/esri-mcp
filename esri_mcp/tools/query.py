"""Feature queries: pagination, date normalization, geometry kept out of context by default."""

import json
from datetime import UTC, datetime
from typing import Any

from esri_mcp.client import EsriClient
from esri_mcp.models import Feature, QueryResult

# Hard cap on total records per tool call — protects the agent's context window
MAX_TOTAL_RECORDS = 5000
# Per-page size when paginating; servers clamp to their own maxRecordCount anyway
PAGE_SIZE = 1000


def _epoch_ms_to_iso(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=UTC).isoformat()
    return value


def _convert_dates(features: list[dict], fields: list[dict]) -> None:
    """Esri returns date fields as epoch milliseconds. Convert in place to ISO 8601."""
    date_fields = [f["name"] for f in fields if f.get("type") == "esriFieldTypeDate"]
    if not date_fields:
        return
    for feat in features:
        attrs = feat.get("attributes", {})
        for name in date_fields:
            if attrs.get(name) is not None:
                attrs[name] = _epoch_ms_to_iso(attrs[name])


async def query_features(
    client: EsriClient,
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    return_geometry: bool = False,
    geometry: dict | None = None,
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    in_sr: int | None = None,
    out_sr: int = 4326,
    order_by: str | None = None,
    max_records: int = MAX_TOTAL_RECORDS,
) -> QueryResult:
    layer_url = layer_url.rstrip("/")
    query_url = f"{layer_url}/query"
    max_records = min(max_records, MAX_TOTAL_RECORDS)

    params: dict[str, Any] = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": str(return_geometry).lower(),
        "outSR": out_sr,
    }
    if return_geometry:
        # Simplify geometry so large polygon sets don't blow up the context window.
        # ~0.0001 deg is ~10m at the equator — fine for LLM consumption.
        params["maxAllowableOffset"] = 0.0001 if out_sr == 4326 else 10
    if geometry is not None:
        params["geometry"] = json.dumps(geometry)
        params["geometryType"] = geometry_type
        params["spatialRel"] = spatial_rel
        if in_sr is not None:
            params["inSR"] = in_sr
    if order_by:
        params["orderByFields"] = order_by

    all_features: list[dict] = []
    fields_meta: list[dict] = []
    offset = 0
    truncated = False

    while True:
        page = dict(params)
        page["resultOffset"] = offset
        page["resultRecordCount"] = min(PAGE_SIZE, max_records - len(all_features))
        body = await client.get_json(query_url, page)

        features = body.get("features", [])
        all_features.extend(features)
        if body.get("fields"):
            fields_meta = body["fields"]

        if len(all_features) >= max_records:
            truncated = bool(body.get("exceededTransferLimit")) or len(all_features) > max_records
            all_features = all_features[:max_records]
            if truncated is False and body.get("exceededTransferLimit"):
                truncated = True
            break
        if not body.get("exceededTransferLimit") or not features:
            break
        offset += len(features)

    _convert_dates(all_features, fields_meta)

    return QueryResult(
        count=len(all_features),
        truncated=truncated,
        features=[
            Feature(attributes=f.get("attributes", {}), geometry=f.get("geometry"))
            for f in all_features
        ],
        source_url=query_url,
    )
