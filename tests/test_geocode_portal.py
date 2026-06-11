import httpx

from esri_mcp.tools.geocode import geocode_address, reverse_geocode
from esri_mcp.tools.portal import get_item_details, search_portal_items
from tests.conftest import json_response, make_client


async def test_geocode_stays_transactional():
    """forStorage must be false — storing results needs a token and different terms."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return json_response(
            {
                "candidates": [
                    {
                        "address": "380 New York St",
                        "location": {"x": -117.19, "y": 34.05},
                        "score": 100,
                    }
                ]
            }
        )

    result = await geocode_address(make_client(handler), "380 New York St, Redlands")
    assert seen["forStorage"] == "false"
    assert result[0].longitude == -117.19


async def test_custom_geocoder_url_override(monkeypatch):
    """ARCGIS_GEOCODER_URL points geocoding at any GeocodeServer, not just AGOL."""
    custom = "https://gis.example.com/arcgis/rest/services/Composite/GeocodeServer"
    monkeypatch.setenv("ARCGIS_GEOCODER_URL", custom)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url.copy_with(query=None))
        return json_response({"candidates": []})

    await geocode_address(make_client(handler), "1 Main St")
    assert seen["url"] == f"{custom}/findAddressCandidates"


async def test_reverse_geocode_parses_address():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "address": {"LongLabel": "380 New York St, Redlands, CA", "City": "Redlands"},
                "location": {"x": -117.195, "y": 34.057},
            }
        )

    result = await reverse_geocode(make_client(handler), -117.195, 34.057)
    assert result.address == "380 New York St, Redlands, CA"
    assert result.raw_address_fields["City"] == "Redlands"


async def test_portal_search_converts_modified_to_iso():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "total": 1234,
                "results": [
                    {
                        "id": "abc123",
                        "title": "USA Counties",
                        "type": "Feature Service",
                        "owner": "esri",
                        "modified": 1717200000000,
                        "tags": ["census"],
                    }
                ],
            }
        )

    result = await search_portal_items(make_client(handler), "counties")
    assert result.total == 1234
    assert result.items[0].modified == "2024-06-01T00:00:00+00:00"


async def test_item_type_filter_in_query():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return json_response({"total": 0, "results": []})

    await search_portal_items(make_client(handler), "parcels", item_type="Feature Service")
    assert seen["q"] == 'parcels AND type:"Feature Service"'


async def test_get_item_details():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/sharing/rest/content/items/abc123" in str(request.url)
        return json_response({"id": "abc123", "title": "X", "type": "Web Map"})

    item = await get_item_details(make_client(handler), "abc123")
    assert item.id == "abc123"
