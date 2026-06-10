"""Service and layer discovery + metadata."""

from esri_mcp.client import EsriClient, EsriError
from esri_mcp.models import FieldInfo, LayerInfo, LayerSummary


def _clean_service_url(service_url: str) -> str:
    return service_url.rstrip("/")


async def list_layers(client: EsriClient, service_url: str) -> list[LayerSummary]:
    body = await client.get_json(_clean_service_url(service_url))
    layers = body.get("layers", []) + body.get("tables", [])
    return [
        LayerSummary(
            id=lyr["id"],
            name=lyr.get("name", f"layer {lyr['id']}"),
            type=lyr.get("type"),
            geometry_type=lyr.get("geometryType"),
        )
        for lyr in layers
    ]


async def get_layer_info(client: EsriClient, service_url: str, layer_id: int) -> LayerInfo:
    service_url = _clean_service_url(service_url)
    layer_url = f"{service_url}/{layer_id}"
    body = await client.get_json(layer_url)

    if "id" not in body:
        # Esri sometimes 200s with an empty-ish body for a bad layer id; make it actionable
        available = await list_layers(client, service_url)
        ids = ", ".join(str(s.id) for s in available) or "none"
        raise EsriError(f"Layer {layer_id} not found on {service_url} — service has layers: {ids}")

    return LayerInfo(
        id=body["id"],
        name=body.get("name", ""),
        description=body.get("description") or None,
        geometry_type=body.get("geometryType"),
        fields=[
            FieldInfo(
                name=f["name"],
                alias=f.get("alias"),
                type=f.get("type", "unknown"),
                length=f.get("length"),
            )
            for f in body.get("fields") or []
        ],
        max_record_count=body.get("maxRecordCount"),
        supports_pagination=bool(
            body.get("advancedQueryCapabilities", {}).get("supportsPagination")
        ),
        extent=body.get("extent"),
        source_url=layer_url,
    )
