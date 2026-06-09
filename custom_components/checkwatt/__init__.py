"""CheckWatt integration."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, CheckwattApiClient
from .const import (
    DOMAIN,
    ENERGY_UPDATE_INTERVAL,
    LOGBOOK_UPDATE_INTERVAL,
    NEWS_UPDATE_INTERVAL,
    PLATFORMS,
    PRICE_UPDATE_INTERVAL,
    REVENUE_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CheckWatt from a config entry."""
    # H2: dedicated session with explicit SSL verification.
    client = CheckwattApiClient(
        async_create_clientsession(hass, verify_ssl=True),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = CheckwattCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class CheckwattCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator that fetches data from the CheckWatt API on a 60-second cycle.

    Expensive or infrequently-changing data (revenue, energy totals, spot prices)
    is refreshed on longer sub-intervals tracked internally.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: CheckwattApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._client = client
        self._entry = entry

        # Cached site identity – fetched once, never changes.
        self._site_id: int | None = None
        self._rpi_serial: str | None = None
        self._price_zone: str | None = None

        # Meter IDs for energy total sensors, filled from energyflow response.
        self._solar_ids: list[int] = []
        self._charge_ids: list[int] = []
        self._discharge_ids: list[int] = []
        self._import_ids: list[int] = []
        self._export_ids: list[int] = []

        self._logbook_raw: str = ""
        self._last_logbook_ts: str | None = None

        # Previous CM10 test status, used to detect transitions.
        self._last_test_status: str | None = None

        # Timestamps tracking when slow-update data was last refreshed.
        self._last_revenue_update: datetime | None = None
        self._last_price_update: datetime | None = None
        self._last_energy_update: datetime | None = None
        self._last_logbook_update: datetime | None = None
        self._last_news_update: datetime | None = None
        self._last_news_ts: str | None = None

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        try:
            await self._client.ensure_authenticated()

            if self._site_id is None:
                await self._bootstrap()

            energy_flow = await self._client.get_energy_flow()
            statuses = await self._client.get_site_statuses(self._rpi_serial)
            status = statuses[0] if statuses else {}

            # Collect meter IDs from the first energyflow response.
            if not self._solar_ids:
                self._solar_ids = energy_flow.get("SolarIds", [])
                self._charge_ids = energy_flow.get("BatteryChargeIds", [])
                self._discharge_ids = energy_flow.get("BatteryDischargeIds", [])
                self._import_ids = energy_flow.get("GridBoughtIds", [])
                self._export_ids = energy_flow.get("GridSoldIds", [])

            test_info: dict = status.get("TestInfo") or {}
            new_test_status = test_info.get("Latest")
            cm10_status_changed = (
                self._last_test_status is not None and new_test_status != self._last_test_status
            )
            cm10_status_prev = self._last_test_status
            if new_test_status is not None:
                self._last_test_status = new_test_status

            data: dict = {
                # Identity
                "site_id": self._site_id,
                "rpi_serial": self._rpi_serial,
                "display_name": status.get("DisplayName"),
                "firmware_version": status.get("Version"),
                # Real-time
                "solar_power_w": energy_flow.get("SolarNow"),
                "battery_power_w": energy_flow.get("BatteryNow"),
                "grid_power_w": energy_flow.get("GridNow"),
                "battery_soc_pct": energy_flow.get("BatterySoC"),
                "last_seen_cm10": status.get("LastSeenCm10"),
                "last_seen_inverter": status.get("LastSeenInverter"),
                "operation_preference": status.get("OperationPreference"),
                "fp_up_kw": status.get("FpUpInKw"),
                "fp_down_kw": status.get("FpDownInKw"),
                "test_info": test_info,
                "logbook_raw": self._logbook_raw,
                # Event signals — reset each cycle, set below if triggered.
                "cm10_status_changed": cm10_status_changed,
                "cm10_status_prev": cm10_status_prev,
                "new_logbook_entries": [],
                "new_news_items": [],
                # Carry over slow-update values from previous cycle.
                **self._slow_data(),
            }

            now = datetime.now(UTC)

            if self._due(self._last_revenue_update, REVENUE_UPDATE_INTERVAL):
                await self._update_revenue(data)
                self._last_revenue_update = now

            if self._due(self._last_price_update, PRICE_UPDATE_INTERVAL):
                await self._update_spot_price(data)
                self._last_price_update = now

            if self._due(self._last_energy_update, ENERGY_UPDATE_INTERVAL):
                await self._update_energy_totals(data)
                self._last_energy_update = now

            if self._due(self._last_logbook_update, LOGBOOK_UPDATE_INTERVAL):
                await self._update_logbook(data)
                self._last_logbook_update = now

            if self._due(self._last_news_update, NEWS_UPDATE_INTERVAL):
                await self._update_news(data)
                self._last_news_update = now

            return data

        except AuthenticationError as err:
            # ConfigEntryAuthFailed triggers HA's reauth flow automatically,
            # both on first refresh and during normal operation.
            raise ConfigEntryAuthFailed(err) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with CheckWatt API: {err}") from err

    # ------------------------------------------------------------------
    # Bootstrap (runs once on first update)
    # ------------------------------------------------------------------

    async def _bootstrap(self) -> None:
        """Fetch site identity from the API. Called once on first update."""
        customer = await self._client.get_customer_details()
        meters = customer.get("Meter", [])
        soc_meter = next((m for m in meters if m.get("InstallationType") == "SoC"), None)
        if soc_meter is None:
            raise UpdateFailed("No SoC meter found in CustomerDetail response")

        serial = soc_meter.get("RpiSerial", "")
        if not serial:
            raise UpdateFailed("RpiSerial missing from SoC meter")

        self._rpi_serial = serial.lower()
        from .sensor import _LOGBOOK_MAX_BYTES

        raw_logbook = soc_meter.get("Logbook") or ""
        self._logbook_raw = raw_logbook[:_LOGBOOK_MAX_BYTES]

        # Seed the logbook timestamp so the first periodic refresh only fires
        # events for entries that appear *after* HA starts.
        from .sensor import _parse_logbook

        _, entries = _parse_logbook(self._logbook_raw)
        if entries:
            self._last_logbook_ts = entries[0].get("timestamp")

        self._site_id = await self._client.get_site_id_by_serial(self._rpi_serial)
        _LOGGER.debug(
            "CheckWatt bootstrap complete: serial=%s site_id=%s",
            self._rpi_serial,
            self._site_id,
        )

    # ------------------------------------------------------------------
    # Slow-update helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _due(last: datetime | None, interval: timedelta) -> bool:
        if last is None:
            return True
        return datetime.now(UTC) - last >= interval

    def _slow_data(self) -> dict:
        """Return previous slow-update values so they survive fast-update cycles."""
        if self.data is None:
            return {
                "today_revenue_sek": None,
                "today_revenue_estimate": False,
                "today_service_name": None,
                "monthly_revenue_sek": None,
                "total_solar_kwh": None,
                "total_import_kwh": None,
                "total_export_kwh": None,
                "total_charge_kwh": None,
                "total_discharge_kwh": None,
                "spot_price_sek_kwh": None,
                "price_zone": None,
            }
        # Note: event signals (cm10_status_changed, new_logbook_entries) are
        # intentionally NOT carried over — they must only fire once per occurrence.
        return {
            k: self.data.get(k)
            for k in (
                "today_revenue_sek",
                "today_revenue_estimate",
                "today_service_name",
                "monthly_revenue_sek",
                "total_solar_kwh",
                "total_import_kwh",
                "total_export_kwh",
                "total_charge_kwh",
                "total_discharge_kwh",
                "spot_price_sek_kwh",
                "price_zone",
            )
        }

    async def _update_revenue(self, data: dict) -> None:
        today = date.today()
        month_start = today.replace(day=1)
        try:
            today_resp = await self._client.get_revenue(
                self._site_id, today.isoformat(), today.isoformat()
            )
            revenues = today_resp.get("Revenue", [])
            if revenues:
                data["today_revenue_sek"] = revenues[0].get("NetRevenue")
                data["today_revenue_estimate"] = revenues[0].get("Estimate", False)
                data["today_service_name"] = revenues[0].get("ServiceName")

            month_resp = await self._client.get_revenue(
                self._site_id, month_start.isoformat(), today.isoformat()
            )
            data["monthly_revenue_sek"] = sum(
                r.get("NetRevenue", 0) for r in month_resp.get("Revenue", [])
            )
        except Exception as err:
            _LOGGER.warning("Revenue update failed (%s): %s", type(err).__name__, err)

    async def _update_spot_price(self, data: dict) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        try:
            if self._price_zone is None:
                self._price_zone = await self._client.get_price_zone()

            resp = await self._client.get_spot_prices(
                self._price_zone, today.isoformat(), tomorrow.isoformat()
            )
            prices = resp.get("Prices", [])
            # Prices are 15-min slots; find the latest slot not after now.
            now_local = datetime.now().replace(tzinfo=None)
            current: float | None = None
            for entry in prices:
                try:
                    slot = datetime.fromisoformat(entry["Date"])
                    if slot <= now_local:
                        current = entry["Value"]
                    else:
                        break
                except (KeyError, ValueError):
                    continue
            data["spot_price_sek_kwh"] = current
            data["price_zone"] = self._price_zone
        except Exception as err:
            _LOGGER.warning("Spot price update failed (%s): %s", type(err).__name__, err)

    async def _update_logbook(self, data: dict) -> None:
        """Re-fetch logbook and detect new entries since last check."""
        from .sensor import _LOGBOOK_MAX_BYTES, _parse_logbook  # avoid circular at module level

        try:
            customer = await self._client.get_customer_details()
            meters = customer.get("Meter", [])
            soc_meter = next((m for m in meters if m.get("InstallationType") == "SoC"), None)
            raw = (soc_meter.get("Logbook") or "") if soc_meter else ""
            if not raw:
                return

            _, entries = _parse_logbook(raw)
            self._logbook_raw = raw[:_LOGBOOK_MAX_BYTES]
            data["logbook_raw"] = raw

            if self._last_logbook_ts is None:
                # First logbook fetch — record latest timestamp but fire no events.
                if entries:
                    self._last_logbook_ts = entries[0].get("timestamp")
                return

            new_entries = [
                e for e in entries if e.get("timestamp") and e["timestamp"] > self._last_logbook_ts
            ]
            if new_entries:
                # Fire oldest-first so automations see them in chronological order.
                data["new_logbook_entries"] = list(reversed(new_entries))
                self._last_logbook_ts = new_entries[0].get("timestamp")
        except Exception as err:
            _LOGGER.warning("Logbook update failed (%s): %s", type(err).__name__, err)

    async def _update_news(self, data: dict) -> None:
        """Fetch news and detect items published since the last check."""
        try:
            items = await self._client.get_news()
            if not items:
                return

            # Sort ascending by timestamp so we can compare and fire oldest-first.
            items.sort(key=lambda x: x.get("Tidstampel", ""))

            if self._last_news_ts is None:
                # First fetch — seed timestamp but fire no events.
                self._last_news_ts = items[-1].get("Tidstampel", "")
                return

            new_items = [i for i in items if i.get("Tidstampel", "") > self._last_news_ts]
            if new_items:
                data["new_news_items"] = new_items
                self._last_news_ts = new_items[-1].get("Tidstampel", "")
        except Exception as err:
            _LOGGER.warning("News update failed (%s): %s", type(err).__name__, err)

    async def _update_energy_totals(self, data: dict) -> None:
        """Sum all-time yearly measurements for each meter group."""
        meter_groups = {
            "total_solar_kwh": self._solar_ids,
            "total_import_kwh": self._import_ids,
            "total_export_kwh": self._export_ids,
            "total_charge_kwh": self._charge_ids,
            "total_discharge_kwh": self._discharge_ids,
        }
        for key, ids in meter_groups.items():
            if not ids:
                continue
            try:
                resp = await self._client.get_energy_totals(ids)
                total_wh = sum(
                    m.get("Value", 0)
                    for meter in resp.get("Meters", [])
                    for m in meter.get("Measurements", [])
                )
                data[key] = round(total_wh / 1000, 3)  # Wh → kWh
            except Exception as err:
                _LOGGER.warning(
                    "Energy total update failed for %s (%s): %s",
                    key,
                    type(err).__name__,
                    err,
                )
