import asyncio
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from app.config import Settings, get_settings
from app.exceptions import (
    PortalAuthError,
    PortalNotFoundError,
    PortalRateLimitError,
    PortalUpstreamError,
)

AUTH_COOKIE_NAME = "__Secure-better-auth.session_token"


class SimpleTTLCache:
    """
    Lightweight, in-memory TTL (Time-To-Live) cache with LRU/eviction support.
    Used to reduce upstream load and honor legacy portal rate limits.
    """

    def __init__(self, ttl_seconds: float, maxsize: int = 2000) -> None:
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            expires_at, val = self._cache[key]
            if time.time() < expires_at:
                return val
            del self._cache[key]
        return None

    def set(self, key: str, val: Any) -> None:
        now = time.time()
        if len(self._cache) >= self.maxsize:
            expired = [k for k, (exp, _) in self._cache.items() if exp <= now]
            for k in expired:
                del self._cache[k]
            if len(self._cache) >= self.maxsize:
                self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (now + self.ttl, val)

    def clear(self) -> None:
        self._cache.clear()


class UrjaPortalClient:
    """
    Asynchronous HTTP client for interacting with the legacy Urja Meter Ops web portal.
    Handles session cookies, automated authentication lifecycle, re-authentication on expiration,
    upstream data extraction, tiered TTL caching, cryptographic HMAC-SHA256 signature generation,
    and bulk exports.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.PORTAL_BASE_URL.rstrip("/")
        self._session_token: Optional[str] = None
        self._signing_secret: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._auth_lock = asyncio.Lock()

        # Tiered TTL Caches:
        # - Metadata (Nameplate, Hierarchy): 5 min (300s)
        # - Geo GIS coordinates: 5 min (300s)
        # - Energy Telemetry: 30 sec buffer
        self._metadata_cache = SimpleTTLCache(ttl_seconds=300.0)
        self._geo_cache = SimpleTTLCache(ttl_seconds=300.0)
        self._energy_cache = SimpleTTLCache(ttl_seconds=30.0)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.settings.REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json, text/html, */*",
                },
            )
            if self._session_token:
                self._client.cookies.set(AUTH_COOKIE_NAME, self._session_token)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session and clear memory caches."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        self._metadata_cache.clear()
        self._geo_cache.clear()
        self._energy_cache.clear()

    async def login(self) -> str:
        """
        Authenticate against Urja Meter Ops portal using SvelteKit action form data.
        Extracts and stores the __Secure-better-auth.session_token cookie.
        """
        async with self._auth_lock:
            client = await self._get_client()
            login_payload = {
                "email": self.settings.PORTAL_USERNAME,
                "password": self.settings.PORTAL_PASSWORD,
            }

            headers = {
                "accept": "application/json",
                "origin": self.base_url,
                "referer": f"{self.base_url}/login",
                "x-sveltekit-action": "true",
            }

            try:
                response = await client.post("/login", data=login_payload, headers=headers)
            except httpx.RequestError as exc:
                raise PortalUpstreamError(f"Network error during authentication: {exc}") from exc

            if response.status_code in (401, 403):
                raise PortalAuthError(
                    f"Authentication rejected by Urja Ops (HTTP {response.status_code}): {response.text[:300]}"
                )

            if response.is_error:
                raise PortalUpstreamError(
                    f"Authentication failed with status {response.status_code}",
                    status_code=response.status_code,
                    details=response.text[:500],
                )

            # Extract session cookie from response cookies or Set-Cookie headers
            token = response.cookies.get(AUTH_COOKIE_NAME)
            if not token:
                token = client.cookies.get(AUTH_COOKIE_NAME)

            if not token:
                for header_val in response.headers.get_list("set-cookie"):
                    if AUTH_COOKIE_NAME in header_val:
                        parts = header_val.split(";")
                        for part in parts:
                            if part.strip().startswith(f"{AUTH_COOKIE_NAME}="):
                                token = part.strip().split("=", 1)[1]
                                break

            if not token:
                raise PortalAuthError(
                    f"Authentication succeeded but '{AUTH_COOKIE_NAME}' cookie was not returned by upstream."
                )

            self._session_token = token
            client.cookies.set(AUTH_COOKIE_NAME, token)
            return token

    async def _ensure_authenticated(self) -> None:
        """Ensures that a valid session token is stored and attached to the client."""
        if not self._session_token:
            await self.login()

    def _handle_response(self, response: httpx.Response) -> httpx.Response:
        """Standardized error boundary for upstream responses."""
        if response.status_code in (401, 403):
            raise PortalAuthError("Upstream authentication failed or session expired.")
        if response.status_code == 404:
            raise PortalNotFoundError("Requested resource not found on Urja Ops.")
        if response.status_code == 429:
            raise PortalRateLimitError("Upstream rate limit reached.")
        if response.is_error:
            raise PortalUpstreamError(
                f"Upstream returned error {response.status_code}",
                status_code=response.status_code,
                details=response.text[:500],
            )
        return response

    async def _authenticated_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Executes an authenticated GET request.
        If a 401/403 is received, invalidates session, re-authenticates, and retries once.
        """
        await self._ensure_authenticated()
        client = await self._get_client()

        req_headers = dict(headers or {})
        if self._session_token:
            client.cookies.set(AUTH_COOKIE_NAME, self._session_token)
            req_headers["Cookie"] = f"{AUTH_COOKIE_NAME}={self._session_token}"

        try:
            response = await client.get(endpoint, params=params, headers=req_headers)
        except httpx.RequestError as exc:
            raise PortalUpstreamError(f"Network error requesting '{endpoint}': {exc}") from exc

        # Handle session expiration gracefully
        if response.status_code in (401, 403):
            self._session_token = None
            await self.login()
            client = await self._get_client()
            if self._session_token:
                client.cookies.set(AUTH_COOKIE_NAME, self._session_token)
                req_headers["Cookie"] = f"{AUTH_COOKIE_NAME}={self._session_token}"
            try:
                response = await client.get(endpoint, params=params, headers=req_headers)
            except httpx.RequestError as exc:
                raise PortalUpstreamError(f"Network error on retry for '{endpoint}': {exc}") from exc

        return self._handle_response(response)

    async def get_signing_secret(self, force_refresh: bool = False) -> str:
        """
        GET /portal/keys
        Retrieves the cryptographic signing secret used for HMAC-SHA256 signature verification.
        """
        if self._signing_secret and not force_refresh:
            return self._signing_secret

        response = await self._authenticated_get("/portal/keys")
        data = response.json()
        secret = (
            data.get("data", {}).get("signingSecret")
            or data.get("signingSecret")
            or data.get("secret")
        )
        if not secret:
            raise PortalUpstreamError("Upstream /portal/keys did not contain 'signingSecret'")
        self._signing_secret = str(secret)
        return self._signing_secret

    async def export_all_meters(self) -> List[Dict[str, Any]]:
        """
        GET /portal/export?page={page}
        Performs signed bulk export of all meters using HMAC-SHA256 headers.
        Paginates through all pages until all meters (total 403) are retrieved.
        """
        secret = await self.get_signing_secret()
        all_meters: List[Dict[str, Any]] = []
        page = 1
        total_count = None

        while True:
            timestamp = str(int(time.time()))
            # Signature payload format: GET\n/portal/export\npage={page}\n{timestamp}
            sig_payload = f"GET\n/portal/export\npage={page}\n{timestamp}"
            signature = hmac.new(
                secret.encode("utf-8"),
                sig_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            headers = {
                "x-timestamp": timestamp,
                "x-signature": signature,
                "Accept": "application/json",
            }

            response = await self._authenticated_get(
                "/portal/export",
                params={"page": page},
                headers=headers,
            )
            res_data = response.json()

            items = res_data.get("data", [])
            if not isinstance(items, list):
                break

            all_meters.extend(items)

            if total_count is None:
                total_count = res_data.get("total", len(items))

            # Stop when all records fetched or no more items returned on current page
            if not items or len(all_meters) >= (total_count or 0):
                break

            page += 1

        return all_meters

    async def get_all_transformers(self) -> List[Dict[str, Any]]:
        """
        GET /portal/dts?page={page}
        Paginates through all Distribution Transformers (total 40) across pages.
        """
        all_dts: List[Dict[str, Any]] = []
        page = 1
        total_count = None

        while True:
            response = await self._authenticated_get(
                "/portal/dts",
                params={"page": page},
            )
            res_data = response.json()
            items = res_data.get("data", [])
            if not isinstance(items, list):
                break

            all_dts.extend(items)

            if total_count is None:
                total_count = res_data.get("total", len(items))

            if not items or len(all_dts) >= (total_count or 0):
                break

            page += 1

        return all_dts

    async def get_meter_energy(self, meter_id: str) -> Dict[str, Any]:
        """
        GET /portal/meters/{meter_id}/energy
        Cached with 30s TTL to preserve telemetry freshness while preventing traffic spikes.
        """
        cached = self._energy_cache.get(meter_id)
        if cached is not None:
            return cached

        response = await self._authenticated_get(f"/portal/meters/{meter_id}/energy")
        data = response.json()
        self._energy_cache.set(meter_id, data)
        return data

    async def get_meter_geo(self, meter_id: str) -> Dict[str, Any]:
        """
        GET /portal/meters/{meter_id}/geo
        Cached with 5-minute TTL (300s) as geographical coordinates are static.
        """
        cached = self._geo_cache.get(meter_id)
        if cached is not None:
            return cached

        response = await self._authenticated_get(f"/portal/meters/{meter_id}/geo")
        data = response.json()
        self._geo_cache.set(meter_id, data)
        return data

    async def get_meter_metadata(self, meter_id: str) -> Dict[str, Any]:
        """
        GET /meters/{meter_id}/__data.json
        Cached with 5-minute TTL (300s) as hardware nameplate and grid topology are static.
        """
        cached = self._metadata_cache.get(meter_id)
        if cached is not None:
            return cached

        response = await self._authenticated_get(f"/meters/{meter_id}/__data.json")
        data = response.json()
        self._metadata_cache.set(meter_id, data)
        return data
