"""CheckWatt integration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, CheckwattApiClient
from .const import (
    API_TZ,
    DIAG_MAX_AGE,
    DIAG_UPDATE_INTERVAL,
    DOMAIN,
    ENERGY_UPDATE_INTERVAL,
    LOGBOOK_UPDATE_INTERVAL,
    NEWS_UPDATE_INTERVAL,
    PLATFORMS,
    PRICE_UPDATE_INTERVAL,
    REVENUE_UPDATE_INTERVAL,
    SLOW_RETRY_INTERVAL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULT_SLOT_LENGTH = timedelta(minutes=15)

# Diagnostics keys cleared when the CM10 has not reported recently.
_DIAG_KEYS = (
    "battery_temp_high_c",
    "battery_temp_low_c",
    "internet_connection",
    "cm10_uptime_s",
    "default_route",
)


def _select_spot_price(prices: list[dict], now_local: datetime) -> float | None:
    """Return the price of the slot covering *now_local*, or None if none does.

    *now_local* must be naive Swedish local time, matching the slot timestamps.
    A slot lasts until the next one starts; the last one is assumed to be as
    long as the one before it, so an outdated price list yields None rather
    than its last price forever.
    """
    current: float | None = None
    current_start: datetime | None = None
    slot_length = _DEFAULT_SLOT_LENGTH
    for entry in prices:
        if not isinstance(entry, dict) or entry.get("Value") is None:
            continue
        try:
            slot = datetime.fromisoformat(entry["Date"])
        except (KeyError, TypeError, ValueError):
            continue
        if slot > now_local:
            return current
        if current_start is not None and slot > current_start:
            slot_length = slot - current_start
        current, current_start = entry["Value"], slot
    if current_start is not None and now_local < current_start + slot_length:
        return current
    return None


def _latest_logbook_ts(entries: list[dict]) -> str | None:
    """Return the newest timestamp among logbook entries, skipping lines without one."""
    return max((e["timestamp"] for e in entries if e.get("timestamp")), default=None)


def _parse_utc(value: str | None) -> datetime | None:
    """Parse an ISO 8601 UTC timestamp such as ``2026-09-16T08:13:35Z``."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (AttributeError, ValueError):
        return None


def _parse_diag_blob(blob: dict) -> dict:
    """Extract HA-relevant values from a connectionStatus Current.Blob.

    Battery temperatures come from the inverter stats; with several inverters
    the highest high and lowest low are reported, matching the EIB UI.
    """
    temps_h: list[float] = []
    temps_l: list[float] = []
    inverter_stats = (blob.get("topics") or {}).get("ems/inverter_stat") or {}
    for inverters in inverter_stats.values():
        if not isinstance(inverters, list):
            continue
        for inv in inverters:
            if not isinstance(inv, dict):
                continue
            if inv.get("temp_h") is not None:
                temps_h.append(inv["temp_h"])
            if inv.get("temp_l") is not None:
                temps_l.append(inv["temp_l"])

    default_route = blob.get("default_route") or []
    if blob.get("hello_eth0"):
        connection = "Network cable (LAN1)"
    elif "ppp0" in default_route:
        connection = "Mobile internet (4G)"
    else:
        connection = "No internet"

    return {
        "battery_temp_high_c": max(temps_h) if temps_h else None,
        "battery_temp_low_c": min(temps_l) if temps_l else None,
        "internet_connection": connection,
        "cm10_uptime_s": blob.get("uptime_s"),
        "default_route": default_route,
    }


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

        # Cached spot price slots; the current slot is re-selected every cycle.
        self._spot_prices: list[dict] = []

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

        # When each slow update is next due; missing means due now.
        self._next_update: dict[str, datetime] = {}
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
            # A missing status (e.g. an empty Statuses list) is not a change —
            # otherwise the event would re-fire every cycle until it's back.
            cm10_status_changed = (
                new_test_status is not None
                and self._last_test_status is not None
                and new_test_status != self._last_test_status
            )
            cm10_status_prev = self._last_test_status
            if new_test_status is not None:
                self._last_test_status = new_test_status

            # Available power the battery can offer CheckWatt right now
            # (the EIB "Available power" panel).
            related_meters = {
                m.get("Type"): m.get("PeakAcKw") for m in status.get("RelatedMeters") or []
            }

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
                "available_charge_kw": related_meters.get("Charging"),
                "available_discharge_kw": related_meters.get("Discharging"),
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
            for name, interval, update in (
                ("revenue", REVENUE_UPDATE_INTERVAL, self._update_revenue),
                ("price", PRICE_UPDATE_INTERVAL, self._update_spot_price),
                ("energy", ENERGY_UPDATE_INTERVAL, self._update_energy_totals),
                ("logbook", LOGBOOK_UPDATE_INTERVAL, self._update_logbook),
                ("diagnostics", DIAG_UPDATE_INTERVAL, self._update_diagnostics),
                ("news", NEWS_UPDATE_INTERVAL, self._update_news),
            ):
                if now < self._next_update.get(name, now):
                    continue
                ok = await update(data)
                # Retry a failed update soon instead of waiting a full interval.
                self._next_update[name] = now + (
                    interval if ok else min(interval, SLOW_RETRY_INTERVAL)
                )

            # Re-select the current 15-min slot every cycle so the sensor
            # doesn't lag behind the hourly price fetch.
            data["spot_price_sek_kwh"] = _select_spot_price(
                self._spot_prices, datetime.now(API_TZ).replace(tzinfo=None)
            )
            data["price_zone"] = self._price_zone

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
        self._last_logbook_ts = _latest_logbook_ts(entries)

        self._site_id = await self._client.get_site_id_by_serial(self._rpi_serial)
        _LOGGER.debug(
            "CheckWatt bootstrap complete: serial=%s site_id=%s",
            self._rpi_serial,
            self._site_id,
        )

    # ------------------------------------------------------------------
    # Slow-update helpers
    # ------------------------------------------------------------------

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
                "battery_temp_high_c": None,
                "battery_temp_low_c": None,
                "internet_connection": None,
                "cm10_uptime_s": None,
                "default_route": None,
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
                "battery_temp_high_c",
                "battery_temp_low_c",
                "internet_connection",
                "cm10_uptime_s",
                "default_route",
            )
        }

    async def _update_revenue(self, data: dict) -> bool:
        today = datetime.now(API_TZ).date()
        month_start = today.replace(day=1)
        try:
            today_resp = await self._client.get_revenue(
                self._site_id, today.isoformat(), today.isoformat()
            )
            revenues = today_resp.get("Revenue", [])
            # Days without data are omitted, so an empty list means nothing
            # earned yet today. Sites running several services get one entry
            # per service.
            data["today_revenue_sek"] = sum(r.get("NetRevenue") or 0 for r in revenues)
            data["today_revenue_estimate"] = any(r.get("Estimate") for r in revenues)
            # The service describes enrollment, not today's earnings — keep the
            # last known one rather than going unavailable every night.
            if services := [r["ServiceName"] for r in revenues if r.get("ServiceName")]:
                data["today_service_name"] = ", ".join(dict.fromkeys(services))

            month_resp = await self._client.get_revenue(
                self._site_id, month_start.isoformat(), today.isoformat()
            )
            # NetRevenue can be an explicit null for unsettled days.
            data["monthly_revenue_sek"] = sum(
                r.get("NetRevenue") or 0 for r in month_resp.get("Revenue", [])
            )
        except Exception as err:
            _LOGGER.warning("Revenue update failed (%s): %s", type(err).__name__, err)
            return False
        return True

    async def _update_spot_price(self, data: dict) -> bool:
        # Use Sweden's "today" — the host may be in a different timezone.
        today = datetime.now(API_TZ).date()
        tomorrow = today + timedelta(days=1)
        try:
            if self._price_zone is None:
                self._price_zone = await self._client.get_price_zone()

            resp = await self._client.get_spot_prices(
                self._price_zone, today.isoformat(), tomorrow.isoformat()
            )
            self._spot_prices = resp.get("Prices", [])
        except Exception as err:
            _LOGGER.warning("Spot price update failed (%s): %s", type(err).__name__, err)
            return False
        return True

    async def _update_logbook(self, data: dict) -> bool:
        """Re-fetch logbook and detect new entries since last check."""
        from .sensor import _LOGBOOK_MAX_BYTES, _parse_logbook  # avoid circular at module level

        try:
            customer = await self._client.get_customer_details()
            meters = customer.get("Meter", [])
            soc_meter = next((m for m in meters if m.get("InstallationType") == "SoC"), None)
            raw = (soc_meter.get("Logbook") or "") if soc_meter else ""
            if not raw:
                return True

            _, entries = _parse_logbook(raw)
            self._logbook_raw = raw[:_LOGBOOK_MAX_BYTES]
            data["logbook_raw"] = raw

            if self._last_logbook_ts is None:
                # First logbook fetch — record latest timestamp but fire no events.
                self._last_logbook_ts = _latest_logbook_ts(entries)
                return True

            new_entries = [
                e for e in entries if e.get("timestamp") and e["timestamp"] > self._last_logbook_ts
            ]
            if new_entries:
                # Fire oldest-first so automations see them in chronological order.
                data["new_logbook_entries"] = list(reversed(new_entries))
                self._last_logbook_ts = _latest_logbook_ts(new_entries)
        except Exception as err:
            _LOGGER.warning("Logbook update failed (%s): %s", type(err).__name__, err)
            return False
        return True

    async def _update_diagnostics(self, data: dict) -> bool:
        """Fetch CM10 diagnostics: battery temperatures and internet connection."""
        try:
            resp = await self._client.get_connection_status(self._site_id)
            current = resp.get("Current") or {}
            blob = json.loads(current["Blob"]) if current.get("Blob") else None
            # Current is the CM10's latest report, however old — an offline
            # CM10 would otherwise show its last connection state forever.
            reported_at = _parse_utc(current.get("Timestamp"))
            if reported_at is not None and datetime.now(UTC) - reported_at > DIAG_MAX_AGE:
                blob = None
            if isinstance(blob, dict):
                data.update(_parse_diag_blob(blob))
            else:
                data.update(dict.fromkeys(_DIAG_KEYS))
        except Exception as err:
            _LOGGER.warning("Diagnostics update failed (%s): %s", type(err).__name__, err)
            return False
        return True

    async def _update_news(self, data: dict) -> bool:
        """Fetch news and detect items published since the last check."""
        try:
            items = await self._client.get_news()
            if not items:
                return True

            # Sort ascending by timestamp so we can compare and fire oldest-first.
            items.sort(key=lambda x: x.get("Tidstampel", ""))

            if self._last_news_ts is None:
                # First fetch — seed timestamp but fire no events.
                self._last_news_ts = items[-1].get("Tidstampel", "")
                return True

            new_items = [i for i in items if i.get("Tidstampel", "") > self._last_news_ts]
            if new_items:
                data["new_news_items"] = new_items
                self._last_news_ts = new_items[-1].get("Tidstampel", "")
        except Exception as err:
            _LOGGER.warning("News update failed (%s): %s", type(err).__name__, err)
            return False
        return True

    async def _update_energy_totals(self, data: dict) -> bool:
        """Sum all-time yearly measurements for each meter group."""
        meter_groups = {
            "total_solar_kwh": self._solar_ids,
            "total_import_kwh": self._import_ids,
            "total_export_kwh": self._export_ids,
            "total_charge_kwh": self._charge_ids,
            "total_discharge_kwh": self._discharge_ids,
        }
        ok = True
        for key, ids in meter_groups.items():
            if not ids:
                continue
            try:
                resp = await self._client.get_energy_totals(ids)
                values = [
                    m.get("Value", 0)
                    for meter in resp.get("Meters", [])
                    for m in meter.get("Measurements", [])
                ]
                if not values:
                    # Publishing 0 would read as a meter reset in HA's
                    # statistics, and the next real value would be counted as
                    # the whole lifetime total again in the Energy dashboard.
                    continue
                total_kwh = round(sum(values) / 1000, 3)  # Wh → kWh
                previous = data.get(key)
                if previous is not None and total_kwh < previous:
                    # Same risk for a partial response: never go backwards.
                    _LOGGER.debug(
                        "Ignoring decrease of %s from %s to %s kWh", key, previous, total_kwh
                    )
                    continue
                data[key] = total_kwh
            except Exception as err:
                _LOGGER.warning(
                    "Energy total update failed for %s (%s): %s",
                    key,
                    type(err).__name__,
                    err,
                )
                ok = False
        return ok
