"""Token acquisition and caching for ArcGIS Online and Enterprise.

Auth mode is selected by which env vars are present, checked in this order:
  1. ARCGIS_USE_NTLM=true + ARCGIS_USERNAME + ARCGIS_PASSWORD -> IWA/NTLM (web-tier auth,
     no tokens; needs the optional httpx-ntlm dependency)
  2. ARCGIS_API_KEY                                      -> static API key
  3. ARCGIS_CLIENT_ID + ARCGIS_CLIENT_SECRET             -> OAuth2 client_credentials (AGOL)
  4. ARCGIS_USERNAME + ARCGIS_PASSWORD + ARCGIS_PORTAL_URL or ARCGIS_TOKEN_URL
       -> legacy generateToken (Enterprise portal, or standalone ArcGIS Server when
          ARCGIS_TOKEN_URL points at {server}/arcgis/tokens/generateToken)
  5. none of the above                                   -> anonymous
"""

import os
import time
from dataclasses import dataclass, field

import httpx

AGOL_TOKEN_URL = "https://www.arcgis.com/sharing/rest/oauth2/token"
REFRESH_MARGIN_SECONDS = 300  # refresh 5 minutes before expiry


class AuthError(Exception):
    """Token acquisition failed. Message never contains the credential itself."""


@dataclass
class TokenManager:
    """Resolves and caches a token for the configured auth mode.

    Reads env vars at construction so tests can monkeypatch os.environ first.
    """

    api_key: str | None = field(default=None, repr=False)
    client_id: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)
    portal_url: str | None = None
    token_url: str | None = None  # explicit generateToken endpoint (standalone ArcGIS Server)
    use_ntlm: bool = False

    _token: str | None = field(default=None, repr=False)
    _expires_at: float = 0.0  # epoch seconds; 0 means no cached token

    @classmethod
    def from_env(cls) -> "TokenManager":
        return cls(
            api_key=os.environ.get("ARCGIS_API_KEY"),
            client_id=os.environ.get("ARCGIS_CLIENT_ID"),
            client_secret=os.environ.get("ARCGIS_CLIENT_SECRET"),
            username=os.environ.get("ARCGIS_USERNAME"),
            password=os.environ.get("ARCGIS_PASSWORD"),
            portal_url=(os.environ.get("ARCGIS_PORTAL_URL") or "").rstrip("/") or None,
            token_url=(os.environ.get("ARCGIS_TOKEN_URL") or "").rstrip("/") or None,
            use_ntlm=(os.environ.get("ARCGIS_USE_NTLM") or "").lower() in {"1", "true", "yes"},
        )

    @property
    def mode(self) -> str:
        if self.use_ntlm and self.username and self.password:
            return "ntlm"
        if self.api_key:
            return "api_key"
        if self.client_id and self.client_secret:
            return "oauth"
        if self.username and self.password and (self.portal_url or self.token_url):
            return "generate_token"
        return "anonymous"

    async def get_token(self, http: httpx.AsyncClient) -> str | None:
        """Return a valid token, or None for anonymous/ntlm modes (ntlm authenticates at
        the transport layer, not via token params)."""
        mode = self.mode
        if mode in ("anonymous", "ntlm"):
            return None
        if mode == "api_key":
            return self.api_key
        if self._token and time.time() < self._expires_at - REFRESH_MARGIN_SECONDS:
            return self._token
        if mode == "oauth":
            await self._fetch_oauth_token(http)
        else:
            await self._fetch_generate_token(http)
        return self._token

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    async def _fetch_oauth_token(self, http: httpx.AsyncClient) -> None:
        resp = await http.post(
            AGOL_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        body = resp.json()
        if "error" in body or "access_token" not in body:
            raise AuthError("OAuth2 token request failed — check ARCGIS_CLIENT_ID/SECRET")
        self._token = body["access_token"]
        self._expires_at = time.time() + float(body.get("expires_in", 1800))

    async def _fetch_generate_token(self, http: httpx.AsyncClient) -> None:
        # Portal: {portal}/sharing/rest/generateToken. Standalone ArcGIS Server has no
        # portal — its endpoint is {server}/arcgis/tokens/generateToken, set explicitly
        # via ARCGIS_TOKEN_URL.
        url = self.token_url or f"{self.portal_url}/sharing/rest/generateToken"
        resp = await http.post(
            url,
            data={
                "username": self.username,
                "password": self.password,
                "client": "referer",
                "referer": "https://esri-mcp.local",  # required by generateToken; value is arbitrary
                "f": "json",
            },
        )
        body = resp.json()
        if "error" in body or "token" not in body:
            raise AuthError(f"generateToken failed against {url} — check ARCGIS_USERNAME/PASSWORD")
        self._token = body["token"]
        # generateToken returns 'expires' as epoch milliseconds
        self._expires_at = float(body["expires"]) / 1000.0
