"""Fixtures: mock-transport clients for offline unit tests.

Integration tests (marked @pytest.mark.integration) hit sampleserver6 directly.
Run offline suite with: uv run pytest -q -m "not integration"
"""

from collections.abc import Callable

import httpx
import pytest

from esri_mcp.auth import TokenManager
from esri_mcp.client import EsriClient


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> EsriClient:
    """EsriClient whose HTTP layer is replaced by a request handler function."""
    client = EsriClient(tokens=TokenManager())  # all-None tokens -> anonymous
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.fixture
def client_factory():
    return make_client


def json_response(body: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=body)
