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


@mcp.resource(
    "esri://catalog/sacramento-layers",
    name="sacramento-layer-catalog",
    description=(
        "Curated, field-verified City of Sacramento GIS layers — URLs and real "
        "(non-alias) field names. Go straight to query_features with these; no "
        "discovery calls needed. Check this before calling search_portal_items "
        "for anything about council districts, park amenities, flood zones, or "
        "address/parcel lookups."
    ),
    mime_type="text/markdown",
)
def sacramento_layer_catalog() -> str:
    return """# City of Sacramento — curated layer catalog

One entry per verified layer: URL, real field names, and a worked example.
Field names below are the queryable names, not the item's display aliases —
always match `where`/`out_fields` against these, not what a UI might show.

## Council Districts (which district + council member)
- Layer: https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/Council_Districts/FeatureServer/0
- Geometry: polygon. Fields: `DISTNUM` (string!), `NAME` (sitting council member)
- Point-in-polygon: geometry={"x": <lon>, "y": <lat>}, geometry_type=esriGeometryPoint, in_sr=4326
- All 8 districts: where="1=1". Note DISTNUM is a string: `DISTNUM = '4'`.

## Public Park Amenities (parks, what's in them, where)
- Layer: https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/Public_Park_Amenities/FeatureServer/0
- Geometry: point. Fields: `ParkName`, `Amenity`, `SubAmenityType`, `AmenityStatus`,
  `CouncilDistrict` (number), `PlanningArea`, `ParkAddress`, `FacilityName`
- One row per amenity (a park appears many times). Example — dog parks in District 4:
  where="Amenity = 'Dog Park' AND CouncilDistrict = 4", out_fields="ParkName,ParkAddress"

## Flood Development Zones (development flood requirements at a location)
- Layer: https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/Flood_Development_Zones/FeatureServer/0
- Geometry: polygon. Fields: `DESCR` (the requirement text)
- This is the City's development-requirement zoning, not FEMA flood insurance
  zones — say which one you're reporting.

## All Addresses (address/parcel lookup, reverse-address, corner resolution)
- Layer: https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/All_Addresses/FeatureServer/2
- Geometry: polygon (one footprint per address, not per parcel — a parcel with
  multiple units/suites has multiple rows sharing one APN).
- Fields: `FULLADDRESS`, `APN` (dashed, e.g. "006-0047-012-0000"), `APN_NODASH`,
  `PARCELID`, `ZIP`, `CITY`
- Useful beyond simple lookup: `APN_NODASH` is the same 14-digit format as the
  `Parcel_No` field on the building-permit tables (BldgPermitIssued_CurrentYear /
  BldgPermitApplied_CurrentYear), so this layer can act as the spatial side of a
  join for "permits near a location" — those permit tables carry no geometry of
  their own. See the intersection-corner-query recipe resource for finding a
  specific building (e.g. "the corner building") rather than every address on a
  block.
"""


@mcp.resource(
    "esri://recipes/intersection-corner-query",
    name="intersection-corner-query-recipe",
    description=(
        "How to answer 'the building on the [northeast/etc] corner of A and B "
        "streets' — resolving a street intersection plus a compass direction to "
        "one specific building. Read this before attempting an intersection or "
        "corner question; a plain point-in-polygon query will not do it."
    ),
    mime_type="text/markdown",
)
def intersection_corner_query_recipe() -> str:
    return """# Resolving "the building on the [corner] of A and B streets"

Two steps — geocode the intersection, then offset a small box toward the
named corner. A single point-in-polygon query is not enough: the geocoded
intersection is the *center* of the crossing, not any one of its four corners.

## Step 1 — geocode the intersection

Call geocode_address with a "Street A & Street B" singleLine query — the AGOL
World Geocoder resolves this as an intersection natively, no special tool or
parameter needed:

    geocode_address(address="J St & 11th St, Sacramento, CA")
    -> "J St & 11th St, Sacramento, California, 95814", score 100
       longitude=-121.492143, latitude=38.579953

## Step 2 — offset a small envelope toward the named corner

The intersection point is the crossing's center. To isolate one corner, query
with a small directional bounding box instead of the point itself — pick the
offset signs from the compass direction (delta ~0.00025 deg, roughly half a
block; widen if nothing comes back):

    NE: xmin=lon,   ymin=lat,   xmax=lon+delta, ymax=lat+delta
    NW: xmin=lon-delta, ymin=lat,   xmax=lon,   ymax=lat+delta
    SE: xmin=lon,   ymin=lat-delta, xmax=lon+delta, ymax=lat
    SW: xmin=lon-delta, ymin=lat-delta, xmax=lon,   ymax=lat

Query the All Addresses layer (see the sacramento-layer-catalog resource) with
that envelope, geometry_type=esriGeometryEnvelope, in_sr=4326:

    query_features(
        layer_url=".../All_Addresses/FeatureServer/2",
        geometry={"xmin": lon, "ymin": lat, "xmax": lon+delta, "ymax": lat+delta},
        geometry_type="esriGeometryEnvelope", in_sr=4326,
        out_fields="FULLADDRESS,APN",
    )

Verified example (NE corner of J St & 11th St): every result shared one APN
(006-0047-012-0000), addressed as both "921 11TH ST" and "1111 J ST" — a single
corner parcel with dual street frontage. Report the FULLADDRESS value(s) that
share the dominant APN in the box; ignore addresses from a different APN that
only clipped the edge of the box.
"""


@mcp.resource(
    "esri://recipes/site-profile",
    name="site-profile-recipe",
    description=(
        "How to answer 'tell me everything about this address' — council "
        "district, zoning, flood zone, historic status, and nearest park in "
        "one answer. Read this before a broad 'what applies at this location' "
        "question; don't stop after the first matching layer."
    ),
    mime_type="text/markdown",
)
def site_profile_recipe() -> str:
    return """# Site profile: "tell me everything about this address"

One geocode, then an independent point-in-polygon query per layer (order
doesn't matter) — combine every result into one answer. A "profile" question
means check every layer below, not just the first one that matches.

## Step 1 — geocode once

    geocode_address(address="915 I St, Sacramento, CA")
    -> longitude=-121.492999960432, latitude=38.582133165832

## Step 2 — point-in-polygon against each layer (see sacramento-layer-catalog
for URLs and full field lists)

Same point geometry every time: geometry={"x": lon, "y": lat},
geometry_type=esriGeometryPoint, in_sr=4326.

- Council_Districts, out_fields="DISTNUM,NAME"
- Flood_Development_Zones, out_fields="DESCR"
- Zoning, out_fields="ZONE,BASE_ZONE,DESCRIPTION"
- Historic_Districts, out_fields="DIST_NAME,STAGE"
- Historic_Landmarks, out_fields="RESOURCE_NAME,HOUSE,STREET_NAME" — an exact
  parcel match here means the building itself is a designated landmark, not
  just inside a historic district; report both if both hit.

## Step 3 — nearest park

Parks are points, not areas you're "inside" — don't expect a point-in-polygon
hit. Use a small envelope around the geocoded point and widen if empty (this
API has no buffer/radius query support today, so an envelope is the
approximation):

    query_features(layer_url=".../Public_Park_Amenities/FeatureServer/0",
        geometry={"xmin": lon-delta, "ymin": lat-delta, "xmax": lon+delta, "ymax": lat+delta},
        geometry_type="esriGeometryEnvelope", in_sr=4326,
        out_fields="ParkName,ParkAddress")

Start delta ~0.0015 (a few blocks); widen if empty. Multiple result rows are
usually the same park (one row per amenity) — dedupe by ParkName.

## Verified example — 915 I St, Sacramento (City Hall)

- Council District 4, represented by Phil Pluckebaum
- Flood zone: "No anticipated flood development requirements"
- Zoning: C-3-SPD (base zone C-3, Central Business District Zone)
- Historic district: Plaza Park (Cesar Chavez), Adopted
- Historic landmark: exact match — "City Hall", 915 I St (the building itself
  is a designated landmark, not merely inside the historic district)
- Nearest park: Cesar E. Chavez Plaza, 910 I St

## Answering

State each finding in prose with which layer it came from. Report a
zero-result layer explicitly ("no flood development requirement applies")
rather than omitting it — a negative result is itself useful, and silently
dropping it reads as though the check wasn't done.
"""


def main() -> None:
    mcp.run(transport="stdio")  # later: mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
