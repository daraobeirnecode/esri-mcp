"""Geocoding via the AGOL World Geocoder, or any GeocodeServer set in
ARCGIS_GEOCODER_URL (Enterprise locator, standalone server, custom-built).
forStorage stays false — storing World Geocoder results requires a token and
different transactional terms; custom locators ignore the param harmlessly."""

import os

from esri_mcp.client import EsriClient, EsriError
from esri_mcp.models import GeocodeCandidate, ReverseGeocodeResult

WORLD_GEOCODER = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer"


def _geocoder_base() -> str:
    return (os.environ.get("ARCGIS_GEOCODER_URL") or WORLD_GEOCODER).rstrip("/")


async def geocode_address(
    client: EsriClient,
    address: str,
    max_results: int = 5,
    country: str | None = None,
) -> list[GeocodeCandidate]:
    params = {
        "singleLine": address,
        "outFields": "Match_addr,Addr_type",
        "maxLocations": max_results,
        "forStorage": "false",
    }
    if country:
        params["sourceCountry"] = country
    body = await client.get_json(f"{_geocoder_base()}/findAddressCandidates", params)
    return [
        GeocodeCandidate(
            address=c.get("address", ""),
            longitude=c["location"]["x"],
            latitude=c["location"]["y"],
            score=c.get("score", 0),
        )
        for c in body.get("candidates", [])
    ]


async def reverse_geocode(
    client: EsriClient, longitude: float, latitude: float
) -> ReverseGeocodeResult:
    params = {
        "location": f"{longitude},{latitude}",
        "forStorage": "false",
    }
    body = await client.get_json(f"{_geocoder_base()}/reverseGeocode", params)
    address = body.get("address")
    if not address:
        raise EsriError(f"no address found near ({longitude}, {latitude})")
    return ReverseGeocodeResult(
        address=address.get("LongLabel") or address.get("Match_addr"),
        longitude=body.get("location", {}).get("x", longitude),
        latitude=body.get("location", {}).get("y", latitude),
        raw_address_fields=address,
    )
