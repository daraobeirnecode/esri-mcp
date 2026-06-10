"""Regression tests for Esri REST gotchas in client.py."""

import httpx
import pytest

from esri_mcp.auth import TokenManager
from esri_mcp.client import EsriClient, EsriError
from tests.conftest import json_response, make_client


async def test_error_in_200_body_raises():
    """Esri returns HTTP 200 for errors — the error key must be detected and raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"error": {"code": 400, "message": "Invalid query", "details": ["bad where clause"]}}
        )

    client = make_client(handler)
    with pytest.raises(EsriError, match="Invalid query"):
        await client.get_json("https://example.com/rest/services/X/MapServer/0/query")


async def test_f_json_always_appended():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return json_response({"ok": True})

    client = make_client(handler)
    await client.get_json("https://example.com/rest/services")
    assert seen["params"]["f"] == "json"


async def test_html_response_raises_clean_error():
    """Esri serves HTML by default — a non-JSON body must not surface a raw traceback."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>ArcGIS REST Services Directory</body></html>")

    client = make_client(handler)
    with pytest.raises(EsriError, match="non-JSON"):
        await client.get_json("https://example.com/rest/services")


async def test_token_error_falls_back_to_anonymous():
    """A bad token on a public endpoint should retry anonymously, not crash."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if "token" in params:
            return json_response({"error": {"code": 498, "message": "Invalid token"}})
        return json_response({"layers": []})

    client = EsriClient(tokens=TokenManager(api_key="stale-key"))
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    body = await client.get_json("https://example.com/rest/services/Public/MapServer")
    assert body == {"layers": []}
    assert len(calls) == 2
    assert "token" in calls[0] and "token" not in calls[1]


async def test_long_request_uses_post():
    """Long where clauses must go as POST (IIS URL-length limits on Enterprise)."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        return json_response({"features": []})

    client = make_client(handler)
    long_where = "OBJECTID IN (" + ",".join(str(i) for i in range(1000)) + ")"
    await client.get_json("https://example.com/MapServer/0/query", {"where": long_where})
    assert seen["method"] == "POST"


async def test_retries_on_transient_failure():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return httpx.Response(503)
        return json_response({"ok": True})

    client = make_client(handler)
    body = await client.get_json("https://example.com/rest/services")
    assert body == {"ok": True}
    assert attempts["n"] == 2
