import time

import httpx

from esri_mcp.auth import TokenManager
from tests.conftest import json_response


def test_mode_precedence():
    assert TokenManager(api_key="k", client_id="c", client_secret="s").mode == "api_key"
    assert TokenManager(client_id="c", client_secret="s").mode == "oauth"
    assert (
        TokenManager(username="u", password="p", portal_url="https://x/portal").mode
        == "generate_token"
    )
    assert TokenManager().mode == "anonymous"
    # Partial credentials don't activate a mode
    assert TokenManager(username="u").mode == "anonymous"


async def test_anonymous_returns_none_without_network():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("anonymous mode must not make token requests")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await TokenManager().get_token(http) is None


async def test_oauth_token_cached_until_refresh_margin():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return json_response({"access_token": f"tok-{calls['n']}", "expires_in": 1800})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tm = TokenManager(client_id="c", client_secret="s")

    assert await tm.get_token(http) == "tok-1"
    assert await tm.get_token(http) == "tok-1"  # cached, no second request
    assert calls["n"] == 1

    # Within 5 minutes of expiry -> refresh
    tm._expires_at = time.time() + 200
    assert await tm.get_token(http) == "tok-2"
    assert calls["n"] == 2


async def test_generate_token_expires_is_epoch_ms():
    expires_ms = (time.time() + 3600) * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sharing/rest/generateToken")
        return json_response({"token": "enterprise-tok", "expires": expires_ms})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tm = TokenManager(username="u", password="p", portal_url="https://portal.example.com/portal")
    assert await tm.get_token(http) == "enterprise-tok"
    assert abs(tm._expires_at - expires_ms / 1000.0) < 1
