"""FastMCP app: tool registration and transport. All transport wiring lives here so
swapping stdio -> streamable-http later is a one-line change in main()."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from esri_mcp.client import EsriClient
from esri_mcp.tools import geocode, layers, portal, query

mcp = FastMCP("esri")

_client: EsriClient | None = None


def get_client() -> EsriClient:
    global _client
    if _client is None:
        _client = EsriClient()
    return _client


@mcp.tool()
async def list_layers(service_url: str) -> list[dict[str, Any]]:
    """List all layers and tables on an ArcGIS MapServer or FeatureServer.

    Use this first when given a service URL, to discover layer ids and names before
    calling get_layer_info or query_features.

    Example: list_layers(service_url="https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer")
    """
    result = await layers.list_layers(get_client(), service_url)
    return [lyr.model_dump() for lyr in result]


@mcp.tool()
async def get_layer_info(service_url: str, layer_id: int) -> dict[str, Any]:
    """Get metadata for one layer: real field names, geometry type, record limits.

    Always call this before query_features — Esri field aliases differ from the real
    queryable field names, and `where` clauses / outFields must use the real names.

    Example: get_layer_info(service_url="https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer", layer_id=3)
    """
    result = await layers.get_layer_info(get_client(), service_url, layer_id)
    return result.model_dump()


@mcp.tool()
async def query_features(
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
    max_records: int = 5000,
) -> dict[str, Any]:
    """Query features from a layer with a SQL where clause and optional spatial filter.

    layer_url is the full layer endpoint (service URL + "/" + layer id). Use
    get_layer_info first to learn real field names; set out_fields to just the fields
    you need ("*" returns everything and wastes context). where="1=1" returns all
    records. Dates come back as ISO 8601 strings, coordinates as lon/lat (WGS84) unless
    out_sr is overridden. Geometry is omitted unless return_geometry=true — only request
    it when actually needed. Spatial filter: pass geometry as Esri JSON (e.g.
    {"xmin":..,"ymin":..,"xmax":..,"ymax":..}) with geometry_type and spatial_rel.
    The result includes count, truncated (true if more records exist), and source_url.

    Example: query_features(layer_url=".../Census/MapServer/3", where="POP2007 > 1000000", out_fields="STATE_NAME,POP2007")
    """
    result = await query.query_features(
        get_client(),
        layer_url,
        where=where,
        out_fields=out_fields,
        return_geometry=return_geometry,
        geometry=geometry,
        geometry_type=geometry_type,
        spatial_rel=spatial_rel,
        in_sr=in_sr,
        out_sr=out_sr,
        order_by=order_by,
        max_records=max_records,
    )
    return result.model_dump(exclude_none=True)


@mcp.tool()
async def geocode_address(
    address: str, max_results: int = 5, country: str | None = None
) -> list[dict[str, Any]]:
    """Convert an address or place name to lon/lat coordinates (AGOL World Geocoder).

    Returns candidates sorted by match score (0-100). Pass country (e.g. "USA") to
    narrow ambiguous matches. Use reverse_geocode for the opposite direction.

    Example: geocode_address(address="380 New York St, Redlands, CA", country="USA")
    """
    result = await geocode.geocode_address(
        get_client(), address, max_results=max_results, country=country
    )
    return [c.model_dump() for c in result]


@mcp.tool()
async def reverse_geocode(longitude: float, latitude: float) -> dict[str, Any]:
    """Convert lon/lat coordinates (WGS84) to the nearest street address.

    Use geocode_address for the opposite direction.

    Example: reverse_geocode(longitude=-117.195, latitude=34.057)
    """
    result = await geocode.reverse_geocode(get_client(), longitude, latitude)
    return result.model_dump()


@mcp.tool()
async def search_portal_items(
    query_text: str, item_type: str | None = None, max_results: int = 10
) -> dict[str, Any]:
    """Search ArcGIS Online (or the configured Enterprise portal) for items.

    Use this to find feature services, maps, and apps by keyword when you don't have a
    service URL yet. item_type filters by Esri item type (e.g. "Feature Service",
    "Web Map"). Items with a url field of type Feature/Map Service can be passed to
    list_layers.

    Example: search_portal_items(query_text="USA counties population", item_type="Feature Service")
    """
    result = await portal.search_portal_items(
        get_client(), query_text, item_type=item_type, max_results=max_results
    )
    return result.model_dump()


@mcp.tool()
async def get_item_details(item_id: str) -> dict[str, Any]:
    """Get full details for one portal item by its 32-char id.

    Use after search_portal_items when you need the item's service url, tags, or
    description.

    Example: get_item_details(item_id="99fd67933e754a1181cc755146be21ca")
    """
    result = await portal.get_item_details(get_client(), item_id)
    return result.model_dump()


def main() -> None:
    mcp.run(transport="stdio")  # later: mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
