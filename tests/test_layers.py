import httpx
import pytest

from esri_mcp.client import EsriError
from esri_mcp.tools.layers import get_layer_info, list_layers
from tests.conftest import json_response, make_client

SERVICE_JSON = {
    "layers": [
        {"id": 0, "name": "Cities", "type": "Feature Layer", "geometryType": "esriGeometryPoint"},
        {"id": 1, "name": "States", "type": "Feature Layer", "geometryType": "esriGeometryPolygon"},
    ],
    "tables": [{"id": 2, "name": "Lookup"}],
}

LAYER_JSON = {
    "id": 1,
    "name": "States",
    "geometryType": "esriGeometryPolygon",
    "maxRecordCount": 1000,
    "advancedQueryCapabilities": {"supportsPagination": True},
    "fields": [
        # Alias differs from real name — the model must get the real name (the
        # Sacramento Parcel_No-vs-APN lesson)
        {"name": "Parcel_No", "alias": "APN", "type": "esriFieldTypeString", "length": 20},
        {"name": "POP2007", "alias": "Population (2007)", "type": "esriFieldTypeInteger"},
    ],
}


async def test_list_layers_includes_tables():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(SERVICE_JSON)

    result = await list_layers(make_client(handler), "https://example.com/X/MapServer/")
    assert [lyr.id for lyr in result] == [0, 1, 2]
    assert result[1].geometry_type == "esriGeometryPolygon"


async def test_get_layer_info_exposes_real_field_names():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(LAYER_JSON)

    info = await get_layer_info(make_client(handler), "https://example.com/X/MapServer", 1)
    assert info.fields[0].name == "Parcel_No"
    assert info.fields[0].alias == "APN"
    assert info.supports_pagination is True


async def test_missing_layer_lists_available_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/9"):
            return json_response({})  # Esri 200s with no layer body
        return json_response(SERVICE_JSON)

    with pytest.raises(EsriError, match=r"Layer 9 not found.*0, 1, 2"):
        await get_layer_info(make_client(handler), "https://example.com/X/MapServer", 9)
