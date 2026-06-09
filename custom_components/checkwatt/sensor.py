"""CheckWatt sensor platform."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CheckwattCoordinator
from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class CheckwattSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value extractor."""

    value_fn: Callable[[dict], StateType | datetime]


_LOGBOOK_EVENT_MAP = {
    "DEACTIVATE": "Deactivated",
    "ACTIVATED": "Activated",
    "FAIL": "Failed",
    "ADJUST": "Adjusted",
}


def _friendly_event(raw_event: str) -> str:
    """Map a raw logbook event tag to a human-readable label."""
    upper = raw_event.upper()
    for key, label in _LOGBOOK_EVENT_MAP.items():
        if key in upper:
            return label
    return raw_event


def _logbook_state(raw: str | None) -> str | None:
    """Return a short state string for the logbook sensor: 'HH:MM · EventLabel'."""
    _, entries = _parse_logbook(raw)
    if not entries:
        return None
    latest = entries[0]
    ts = latest.get("timestamp")
    time_part = ts[11:16] if ts and len(ts) >= 16 else ts or "?"
    return f"{time_part} · {_friendly_event(latest['event'].split(' / ')[0])}"


def _op_pref_label(pref: str | None) -> str | None:
    if pref is None:
        return None
    return {"co": "Currently Optimized", "sc": "Self Consumption"}.get(pref, pref)


_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_EVENT_RE = re.compile(r"\[([^\]]+)\]")


_LOGBOOK_MAX_BYTES = 65_536


def _parse_logbook(raw: str | None) -> tuple[str | None, list[dict]]:
    """Parse the Logbook string into (latest_event, list_of_entries).

    Each entry: {"event": str, "timestamp": str | None, "detail": str}.
    Capped at 25 most recent entries (logbook is newest-first).
    """
    if not raw:
        return None, []
    # L2/L3: cap size before regex to bound memory and backtracking time.
    if len(raw) > _LOGBOOK_MAX_BYTES:
        raw = raw[:_LOGBOOK_MAX_BYTES]
    entries = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        events = [m.group(1).strip() for m in _EVENT_RE.finditer(line)]
        ts_m = _TS_RE.search(line)
        timestamp = ts_m.group(1) if ts_m else None
        # Detail = line minus all bracketed tags and the timestamp
        detail = _EVENT_RE.sub("", line)
        if ts_m:
            detail = detail.replace(ts_m.group(1), "")
        detail = re.sub(r"\s{2,}", " ", detail).strip()
        detail = re.sub(r"\s*API-BACKEND\s*$", "", detail, flags=re.IGNORECASE).strip("- ").strip()
        entries.append(
            {
                "event": " / ".join(events) if events else line[:60],
                "timestamp": timestamp,
                "detail": detail,
            }
        )
        if len(entries) == 25:
            break
    return entries[0]["event"] if entries else None, entries


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(UTC)
    except ValueError:
        return None


SENSOR_DESCRIPTIONS: tuple[CheckwattSensorDescription, ...] = (
    # ---- Real-time power ----------------------------------------------------
    CheckwattSensorDescription(
        key="solar_power_w",
        translation_key="solar_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("solar_power_w"),
    ),
    CheckwattSensorDescription(
        key="battery_power_w",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        # Positive = charging, negative = discharging (matches API convention).
        value_fn=lambda d: d.get("battery_power_w"),
    ),
    CheckwattSensorDescription(
        key="grid_power_w",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        # Negative = exporting to grid.
        value_fn=lambda d: d.get("grid_power_w"),
    ),
    CheckwattSensorDescription(
        key="battery_soc_pct",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("battery_soc_pct"),
    ),
    # ---- Revenue ------------------------------------------------------------
    CheckwattSensorDescription(
        key="today_revenue_sek",
        translation_key="today_revenue",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="SEK",
        suggested_display_precision=2,
        value_fn=lambda d: d.get("today_revenue_sek"),
    ),
    CheckwattSensorDescription(
        key="monthly_revenue_sek",
        translation_key="monthly_revenue",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="SEK",
        suggested_display_precision=2,
        value_fn=lambda d: d.get("monthly_revenue_sek"),
    ),
    # ---- Spot price ---------------------------------------------------------
    CheckwattSensorDescription(
        key="spot_price_sek_kwh",
        translation_key="spot_price",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="SEK/kWh",
        suggested_display_precision=3,
        value_fn=lambda d: d.get("spot_price_sek_kwh"),
    ),
    CheckwattSensorDescription(
        key="spot_price_incl_vat",
        translation_key="spot_price_incl_vat",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="SEK/kWh",
        suggested_display_precision=3,
        value_fn=lambda d: (
            round(d["spot_price_sek_kwh"] * 1.25, 4)
            if d.get("spot_price_sek_kwh") is not None
            else None
        ),
    ),
    # ---- Energy totals (for HA Energy dashboard) ----------------------------
    CheckwattSensorDescription(
        key="total_solar_kwh",
        translation_key="total_solar_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("total_solar_kwh"),
    ),
    CheckwattSensorDescription(
        key="total_import_kwh",
        translation_key="total_grid_import",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("total_import_kwh"),
    ),
    CheckwattSensorDescription(
        key="total_export_kwh",
        translation_key="total_grid_export",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("total_export_kwh"),
    ),
    CheckwattSensorDescription(
        key="total_charge_kwh",
        translation_key="total_battery_charge",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("total_charge_kwh"),
    ),
    CheckwattSensorDescription(
        key="total_discharge_kwh",
        translation_key="total_battery_discharge",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("total_discharge_kwh"),
    ),
    # ---- Status -------------------------------------------------------------
    CheckwattSensorDescription(
        key="cm10_status",
        translation_key="cm10_status",
        icon="mdi:raspberry-pi",
        value_fn=lambda d: d.get("test_info", {}).get("Latest"),
    ),
    CheckwattSensorDescription(
        key="last_seen_cm10",
        translation_key="last_seen_cm10",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _parse_dt(d.get("last_seen_cm10")),
    ),
    CheckwattSensorDescription(
        key="last_seen_inverter",
        translation_key="last_seen_inverter",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _parse_dt(d.get("last_seen_inverter")),
    ),
    CheckwattSensorDescription(
        key="operation_preference",
        translation_key="operation_mode",
        icon="mdi:tune",
        value_fn=lambda d: _op_pref_label(d.get("operation_preference")),
    ),
    CheckwattSensorDescription(
        key="today_service_name",
        translation_key="active_service",
        icon="mdi:transmission-tower",
        value_fn=lambda d: d.get("today_service_name"),
    ),
    CheckwattSensorDescription(
        key="price_zone",
        translation_key="price_zone",
        icon="mdi:map-marker",
        value_fn=lambda d: d.get("price_zone"),
    ),
    CheckwattSensorDescription(
        key="logbook",
        translation_key="logbook",
        icon="mdi:notebook-outline",
        value_fn=lambda d: _logbook_state(d.get("logbook_raw")),
    ),
    CheckwattSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        icon="mdi:chip",
        value_fn=lambda d: d.get("firmware_version"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CheckWatt sensors from a config entry."""
    coordinator: CheckwattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CheckwattSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class CheckwattSensor(CoordinatorEntity[CheckwattCoordinator], SensorEntity):
    """A sensor that reads from the CheckWatt coordinator."""

    entity_description: CheckwattSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CheckwattCoordinator,
        description: CheckwattSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.data.get("rpi_serial", "unknown")
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=coordinator.data.get("display_name") or "CheckWatt",
            manufacturer="CheckWatt",
            model="CM10",
            sw_version=coordinator.data.get("firmware_version"),
            configuration_url="https://energyinbalance.se",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.native_value is not None

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        key = self.entity_description.key
        if key == "cm10_status":
            ti = self.coordinator.data.get("test_info", {})
            return {
                "result": ti.get("Result"),
                "failed_in_a_row": ti.get("FailedInARow"),
            }
        if key == "logbook":
            _, entries = _parse_logbook(self.coordinator.data.get("logbook_raw"))
            recent = [
                {
                    "timestamp": e.get("timestamp"),
                    "event": _friendly_event(e["event"].split(" / ")[0]),
                    "detail": e.get("detail") or None,
                }
                for e in entries[:5]
            ]
            return {"recent_entries": recent}
        return None
