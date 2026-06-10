"""Live tests against Esri's public sampleserver6. Run with: uv run pytest -m integration"""

import pytest

from esri_mcp.client import EsriClient
from esri_mcp.tools.layers import get_layer_info, list_layers
from esri_mcp.tools.query import query_features

pytestmark = pytest.mark.integration

CENSUS = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer"


@pytest.fixture
async def client():
    c = EsriClient()
    yield c
    await c.aclose()


async def test_list_layers_census(client):
    layers = await list_layers(client, CENSUS)
    assert any(lyr.name for lyr in layers)
    assert all(isinstance(lyr.id, int) for lyr in layers)


async def test_layer_info_has_real_field_names(client):
    layers = await list_layers(client, CENSUS)
    info = await get_layer_info(client, CENSUS, layers[0].id)
    assert info.fields, "expected at least one field"
    assert info.source_url.endswith(f"/{layers[0].id}")


async def test_query_returns_attributes_without_geometry(client):
    layers = await list_layers(client, CENSUS)
    info = await get_layer_info(client, CENSUS, layers[0].id)
    first_field = info.fields[0].name
    result = await query_features(client, info.source_url, out_fields=first_field, max_records=5)
    assert result.count > 0
    assert result.features[0].geometry is None
    assert first_field in result.features[0].attributes
