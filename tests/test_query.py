"""Regression tests for pagination, date conversion, and context-window protection."""

import httpx

from esri_mcp.tools.query import query_features
from tests.conftest import json_response, make_client

DATE_FIELDS = [
    {"name": "NAME", "type": "esriFieldTypeString"},
    {"name": "ISSUED", "type": "esriFieldTypeDate"},
]


async def test_epoch_dates_converted_to_iso():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "fields": DATE_FIELDS,
                "features": [
                    {"attributes": {"NAME": "permit-1", "ISSUED": 1717200000000}},
                    {"attributes": {"NAME": "permit-2", "ISSUED": None}},
                ],
            }
        )

    result = await query_features(make_client(handler), "https://example.com/MapServer/0")
    assert result.features[0].attributes["ISSUED"] == "2024-06-01T00:00:00+00:00"
    assert result.features[1].attributes["ISSUED"] is None


async def test_pagination_loops_until_transfer_limit_clear():
    """Server pages of 2 with exceededTransferLimit must be stitched together."""
    pages = [
        {
            "features": [{"attributes": {"ID": 1}}, {"attributes": {"ID": 2}}],
            "exceededTransferLimit": True,
        },
        {
            "features": [{"attributes": {"ID": 3}}, {"attributes": {"ID": 4}}],
            "exceededTransferLimit": True,
        },
        {"features": [{"attributes": {"ID": 5}}]},
    ]
    offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offsets.append(request.url.params["resultOffset"])
        return json_response(pages[len(offsets) - 1])

    result = await query_features(make_client(handler), "https://example.com/MapServer/0")
    assert result.count == 5
    assert result.truncated is False
    assert offsets == ["0", "2", "4"]


async def test_total_record_cap_marks_truncated():
    """A query that would exceed max_records stops and flags truncation for the agent."""

    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params["resultRecordCount"])
        return json_response(
            {
                "features": [{"attributes": {"ID": i}} for i in range(n)],
                "exceededTransferLimit": True,
            }
        )

    result = await query_features(
        make_client(handler), "https://example.com/MapServer/0", max_records=250
    )
    assert result.count == 250
    assert result.truncated is True


async def test_geometry_off_by_default_and_outsr_4326():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return json_response({"features": []})

    await query_features(make_client(handler), "https://example.com/MapServer/0")
    assert seen["returnGeometry"] == "false"
    assert seen["outSR"] == "4326"
    assert "maxAllowableOffset" not in seen


async def test_spatial_filter_params_serialized():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return json_response({"features": []})

    await query_features(
        make_client(handler),
        "https://example.com/MapServer/0",
        geometry={"xmin": -118, "ymin": 33, "xmax": -117, "ymax": 34},
        in_sr=4326,
    )
    assert seen["geometryType"] == "esriGeometryEnvelope"
    assert seen["spatialRel"] == "esriSpatialRelIntersects"
    assert seen["inSR"] == "4326"
    assert '"xmin"' in seen["geometry"]
