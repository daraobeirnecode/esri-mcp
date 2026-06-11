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
    # Standalone ArcGIS Server: token_url works in place of portal_url
    assert (
        TokenManager(username="u", password="p", token_url="https://srv:6443/arcgis/tokens").mode
        == "generate_token"
    )
    # Explicit NTLM opt-in beats everything else
    assert TokenManager(username="DOM\\u", password="p", api_key="k", use_ntlm=True).mode == "ntlm"
    # NTLM flag without credentials is not NTLM
    assert TokenManager(use_ntlm=True).mode == "anonymous"


def test_token_scoping_by_host():
    """Credentials apply only to their home host — everything else goes anonymous."""
    # AGOL credentials cover *.arcgis.com only
    agol = TokenManager(api_key="k")
    assert agol.applies_to("https://services.arcgis.com/abc/FeatureServer") is True
    assert agol.applies_to("https://www.arcgis.com/sharing/rest/search") is True
    assert agol.applies_to("https://gis.some-county.gov/arcgis/rest/services") is False
    assert agol.applies_to("https://evilarcgis.com/steal") is False  # suffix, not subdomain

    # Enterprise token covers the portal host only
    ent = TokenManager(username="u", password="p", portal_url="https://portal.example.com/portal")
    assert ent.applies_to("https://portal.example.com/server/rest/services/X") is True
    assert ent.applies_to("https://www.arcgis.com/sharing/rest/search") is False

    # Federated deployments opt extra hosts in via ARCGIS_TOKEN_HOSTS
    fed = TokenManager(
        username="u",
        password="p",
        portal_url="https://portal.example.com/portal",
        extra_token_hosts=("gis.example.com",),
    )
    assert fed.applies_to("https://gis.example.com/server/rest/services/X") is True

    # Standalone server token covers the token-endpoint host
    srv = TokenManager(
        username="u", password="p", token_url="https://srv.example.com:6443/arcgis/tokens"
    )
    assert srv.applies_to("https://srv.example.com:6443/arcgis/rest/services/X") is True
    assert srv.applies_to("https://other.example.org/arcgis/rest/services/X") is False

    # Anonymous and NTLM never attach tokens
    assert TokenManager().applies_to("https://www.arcgis.com/x") is False
    ntlm = TokenManager(username="DOM\\u", password="p", use_ntlm=True)
    assert ntlm.applies_to("https://gis.corp.local/arcgis/rest/services") is False


async def test_ntlm_mode_returns_no_token():
    """NTLM authenticates at the transport layer — no token params, no token requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("ntlm mode must not make token requests")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tm = TokenManager(username="DOM\\u", password="p", use_ntlm=True)
    assert await tm.get_token(http) is None


async def test_standalone_server_token_url_used():
    """ARCGIS_TOKEN_URL must override the portal-style generateToken path."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return json_response({"token": "srv-tok", "expires": (time.time() + 3600) * 1000})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tm = TokenManager(
        username="u",
        password="p",
        token_url="https://srv.example.com:6443/arcgis/tokens/generateToken",
    )
    assert await tm.get_token(http) == "srv-tok"
    assert seen["url"] == "https://srv.example.com:6443/arcgis/tokens/generateToken"


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
