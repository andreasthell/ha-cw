"""CheckWatt API client."""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime, timedelta

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.checkwatt.se"
_SUNHORIZON_URL = "https://sunhorizon-app-api2-f4640054350f.herokuapp.com"
_JWT_BUFFER = timedelta(minutes=5)
_REFRESH_BUFFER = timedelta(hours=1)
_REQUEST_TIMEOUT = ClientTimeout(total=10)  # L1: use ClientTimeout, not bare int


class AuthenticationError(Exception):
    """Raised when credentials are invalid or tokens cannot be refreshed."""


class CheckwattApiClient:
    """Async client for the CheckWatt / EnergyInBalance API.

    The caller is responsible for providing and closing the aiohttp session.
    Tokens are cached in memory; a full re-login is performed on first use only.
    When both tokens have expired, AuthenticationError is raised so the caller
    can trigger a HA reauth flow instead of retrying with a cached password.
    """

    def __init__(self, session: ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._jwt: str | None = None
        self._jwt_expiry: datetime | None = None
        self._refresh: str | None = None
        self._refresh_expiry: datetime | None = None

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _jwt_valid(self) -> bool:
        return bool(
            self._jwt and self._jwt_expiry and datetime.now(UTC) < self._jwt_expiry - _JWT_BUFFER
        )

    def _refresh_valid(self) -> bool:
        return bool(
            self._refresh
            and self._refresh_expiry
            and datetime.now(UTC) < self._refresh_expiry - _REFRESH_BUFFER
        )

    def _store_tokens(self, data: dict) -> None:
        self._jwt = data["JwtToken"]
        self._refresh = data["RefreshToken"]

        # H4: decode JWT expiry but cap at 24 h to guard against tampered tokens.
        try:
            payload_b64 = self._jwt.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            claims = json.loads(base64.b64decode(payload_b64))
            raw_expiry = datetime.fromtimestamp(claims["exp"], tz=UTC)
            max_expiry = datetime.now(UTC) + timedelta(hours=24)
            self._jwt_expiry = min(raw_expiry, max_expiry)
        except Exception:
            # JWTs are only valid ~15 minutes since the 2026-09 API change,
            # so a decode failure must assume a short lifetime.
            self._jwt_expiry = datetime.now(UTC) + timedelta(minutes=10)

        try:
            self._refresh_expiry = datetime.fromisoformat(
                data["RefreshTokenExpires"].replace("Z", "+00:00")
            )
        except Exception:
            self._refresh_expiry = datetime.now(UTC) + timedelta(days=7)

    async def _do_login(self) -> None:
        creds = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        try:
            async with self._session.post(
                f"{BASE_URL}/user/Login?audience=eib",
                headers={
                    "authorization": f"Basic {creds}",
                    "content-type": "application/json",
                },
                json={"OneTimePassword": ""},
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 401:
                    raise AuthenticationError("Invalid username or password")
                resp.raise_for_status()
                self._store_tokens(await resp.json())
        except AuthenticationError:
            raise
        except (ClientResponseError, ClientError) as err:
            raise ConnectionError(f"Login request failed: {type(err).__name__}") from err

    async def _do_refresh(self) -> None:
        try:
            async with self._session.get(
                f"{BASE_URL}/user/RefreshToken?audience=eib",
                headers={"authorization": f"Bearer {self._refresh}"},
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 401:
                    # Refresh token expired — fall back to full login.
                    self._refresh = None
                    await self._do_login()
                    return
                resp.raise_for_status()
                self._store_tokens(await resp.json())
        except AuthenticationError:
            raise
        except (ClientResponseError, ClientError) as err:
            raise ConnectionError(f"Token refresh failed: {type(err).__name__}") from err

    async def ensure_authenticated(self) -> None:
        """Ensure a valid JWT is available, refreshing silently when needed."""
        if self._jwt_valid():
            return
        if self._refresh_valid():
            await self._do_refresh()
        else:
            await self._do_login()

    async def validate_credentials(self) -> None:
        """Perform a login to verify credentials. Raises AuthenticationError on failure."""
        await self._do_login()

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict:
        return {"authorization": f"Bearer {self._jwt}"}

    def _invalidate_jwt_on_401(self, status: int) -> None:
        """Drop a server-rejected JWT so the next cycle re-authenticates
        instead of retrying the locally-still-valid token until it expires."""
        if status == 401:
            self._jwt = None
            self._jwt_expiry = None

    async def _get(self, path: str, params: dict | list | None = None) -> dict | list:
        """GET request. Use *params* for query parameters — aiohttp encodes them safely."""
        url = f"{BASE_URL}{path}"
        try:
            async with self._session.get(
                url,
                headers=self._auth_headers(),
                params=params,
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                self._invalidate_jwt_on_401(resp.status)
                resp.raise_for_status()
                return await resp.json()
        except (ClientResponseError, ClientError) as err:
            # L4: omit query params from error message to avoid leaking values.
            raise ConnectionError(f"Request to {path} failed: {type(err).__name__}") from err

    async def _get_text(self, path: str) -> str:
        url = f"{BASE_URL}{path}"
        try:
            async with self._session.get(
                url, headers=self._auth_headers(), timeout=_REQUEST_TIMEOUT
            ) as resp:
                self._invalidate_jwt_on_401(resp.status)
                resp.raise_for_status()
                return (await resp.text()).strip()
        except (ClientResponseError, ClientError) as err:
            raise ConnectionError(f"Request to {path} failed: {type(err).__name__}") from err

    # ------------------------------------------------------------------
    # API endpoints
    # H3/M2: all query parameters passed via *params* so aiohttp URL-encodes them.
    # ------------------------------------------------------------------

    async def get_customer_details(self) -> dict:
        return await self._get("/controlpanel/CustomerDetail")

    async def get_site_id_by_serial(self, serial: str) -> int:
        data = await self._get("/Site/SiteIdBySerial", params={"serial": serial})
        return data["SiteId"]

    async def get_site_details(self, site_id: int) -> dict:
        return await self._get(f"/site/{site_id}")

    async def get_site_statuses(self, serial: str) -> list:
        return await self._get("/site/Statuses", params={"serial": serial})

    async def get_energy_flow(self) -> dict:
        return await self._get("/ems/energyflow")

    async def get_price_zone(self) -> str:
        return await self._get_text("/ems/pricezone")

    async def get_spot_prices(self, zone: str, from_date: str, to_date: str) -> dict:
        return await self._get(
            "/ems/spotprice",
            params={"zone": zone, "fromDate": from_date, "toDate": to_date},
        )

    async def get_revenue(self, site_id: int, from_date: str, to_date: str) -> dict:
        return await self._get(
            f"/revenue/{site_id}",
            params={"from": from_date, "to": to_date, "resolution": "day"},
        )

    async def get_news(self) -> list:
        """Fetch EIB news items. No auth sent — endpoint is public."""
        url = f"{_SUNHORIZON_URL}/cw/eib-news"
        try:
            async with self._session.get(
                url,
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except (ClientResponseError, ClientError) as err:
            raise ConnectionError(f"News request failed: {type(err).__name__}") from err

    async def get_energy_totals(self, meter_ids: list[int]) -> dict:
        """Fetch all-time yearly-grouped totals for the given meter IDs."""
        from datetime import date

        year = date.today().year
        # aiohttp accepts a list of tuples for repeated query parameters.
        params: list[tuple[str, str | int]] = [
            ("grouping", "3"),
            ("fromdate", "1900"),
            ("todate", str(year)),
        ]
        params += [("meterId", mid) for mid in meter_ids]
        return await self._get("/datagrouping/series", params=params)
