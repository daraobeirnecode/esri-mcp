"""httpx wrapper for ArcGIS REST: f=json, error normalization, retries, auth fallback."""

import asyncio
from typing import Any

import httpx

from esri_mcp.auth import TokenManager

# Esri error codes that mean "token problem", not "request problem"
TOKEN_ERROR_CODES = {498, 499}
# URLs longer than this switch to POST (IIS-fronted Enterprise servers reject long GETs)
MAX_GET_URL_LENGTH = 2000
RETRYABLE_STATUS = {502, 503, 504}
MAX_RETRIES = 2


class EsriError(Exception):
    """Normalized error from an Esri JSON body or transport failure."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class EsriClient:
    """One client per server process. Esri returns HTTP 200 for errors, so every
    response body is checked for an `error` key and raised from."""

    def __init__(self, tokens: TokenManager | None = None, timeout: float = 30.0):
        self.tokens = tokens or TokenManager.from_env()
        self._http = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET (or POST if the query string would be too long) with f=json appended,
        token injected, error-in-200 raised, and anonymous fallback on token failure."""
        params = dict(params or {})
        params["f"] = "json"

        token = await self.tokens.get_token(self._http)
        if token:
            params["token"] = token

        body = await self._request(url, params)

        if "error" in body:
            err = body["error"]
            code = err.get("code")
            # Public endpoints shouldn't fail because our token is bad/expired —
            # fall back to anonymous rather than crash.
            if code in TOKEN_ERROR_CODES and token:
                self.tokens.invalidate()
                params.pop("token", None)
                body = await self._request(url, params)
                if "error" not in body:
                    return body
                err = body["error"]
                code = err.get("code")
            details = "; ".join(err.get("details") or [])
            message = err.get("message") or "unknown Esri error"
            raise EsriError(f"{message}{f' ({details})' if details else ''}", code=code)

        return body

    async def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        use_post = len(str(httpx.URL(url, params=params))) > MAX_GET_URL_LENGTH

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                if use_post:
                    resp = await self._http.post(url, data=params)
                else:
                    resp = await self._http.get(url, params=params)
                if resp.status_code in RETRYABLE_STATUS:
                    raise EsriError(f"server returned HTTP {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, EsriError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as exc:
                raise EsriError(
                    f"HTTP {exc.response.status_code} from {url}",
                    code=exc.response.status_code,
                ) from exc
            except ValueError as exc:  # non-JSON body (Esri HTML error page)
                raise EsriError(
                    f"non-JSON response from {url} — is this an ArcGIS REST endpoint?"
                ) from exc

        raise EsriError(f"request to {url} failed after {MAX_RETRIES + 1} attempts: {last_exc}")
