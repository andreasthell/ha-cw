"""CheckWatt event platform."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CheckwattCoordinator
from .const import DOMAIN


def _map_news_event_type(category: str) -> str:
    c = category.lower()
    if c == "nyheter":
        return "news"
    if c == "uppdatering":
        return "update"
    return "other"


def _map_logbook_event_type(event: str) -> str:
    e = event.upper()
    if "DEACTIVATE" in e:
        return "deactivated"
    if "ACTIVATED" in e:
        return "activated"
    if "FAIL" in e:
        return "failed"
    if "ADJUST" in e:
        return "adjusted"
    return "other"


def _map_cm10_event_type(status: str | None) -> str:
    if not status:
        return "other"
    s = status.upper()
    if "DEACTIVATE" in s:
        return "deactivated"
    if "ACTIVATED" in s:
        return "activated"
    if "FAIL" in s:
        return "failed"
    return "other"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CheckWatt event entities from a config entry."""
    coordinator: CheckwattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            CheckwattCm10StatusEvent(coordinator),
            CheckwattLogbookEvent(coordinator),
            CheckwattNewsEvent(coordinator),
        ]
    )


class _CheckwattEventBase(CoordinatorEntity[CheckwattCoordinator], EventEntity):
    """Base class for CheckWatt event entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CheckwattCoordinator) -> None:
        super().__init__(coordinator)
        serial = coordinator.data.get("rpi_serial", "unknown")
        self._attr_unique_id = f"{serial}_{self._key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
        )

    @property
    def _key(self) -> str:
        raise NotImplementedError

    def _handle_coordinator_update(self) -> None:
        # Listeners also run after failed refreshes, where coordinator.data
        # still holds the previous payload — skip processing so the same
        # event signals don't fire again on every failed cycle.
        if self.coordinator.last_update_success:
            self._process_update(self.coordinator.data)
        super()._handle_coordinator_update()

    def _process_update(self, data: dict) -> None:
        raise NotImplementedError


class CheckwattCm10StatusEvent(_CheckwattEventBase):
    """Fires when CM10 TestInfo.Latest changes."""

    _attr_translation_key = "cm10_test_status"
    _attr_icon = "mdi:raspberry-pi"
    _attr_event_types = ["activated", "deactivated", "failed", "other"]

    @property
    def _key(self) -> str:
        return "cm10_test_status"

    def _process_update(self, data: dict) -> None:
        if not data.get("cm10_status_changed"):
            return
        ti = data.get("test_info", {})
        status = ti.get("Latest")
        self._trigger_event(
            _map_cm10_event_type(status),
            {
                "status": status,
                "result": ti.get("Result"),
                "failed_in_a_row": ti.get("FailedInARow"),
                "previous_status": data.get("cm10_status_prev"),
            },
        )


class CheckwattLogbookEvent(_CheckwattEventBase):
    """Fires for each new logbook entry detected."""

    _attr_translation_key = "logbook_event"
    _attr_icon = "mdi:notebook-outline"
    _attr_event_types = ["activated", "deactivated", "failed", "adjusted", "other"]

    @property
    def _key(self) -> str:
        return "logbook_event"

    def _process_update(self, data: dict) -> None:
        for entry in data.get("new_logbook_entries", []):
            self._trigger_event(
                _map_logbook_event_type(entry.get("event", "")),
                {
                    "event": entry.get("event"),
                    "timestamp": entry.get("timestamp"),
                    "detail": entry.get("detail"),
                },
            )


class CheckwattNewsEvent(_CheckwattEventBase):
    """Fires for each new EIB news item."""

    _attr_translation_key = "news_event"
    _attr_icon = "mdi:newspaper-variant-outline"
    _attr_event_types = ["news", "update", "other"]

    @property
    def _key(self) -> str:
        return "news_event"

    def _process_update(self, data: dict) -> None:
        for item in data.get("new_news_items", []):
            title = item.get("RubrikEN") or item.get("Rubrik", "")
            self._trigger_event(
                _map_news_event_type(item.get("Kategori", "")),
                {
                    "title": title,
                    "title_sv": item.get("Rubrik", ""),
                    "title_en": item.get("RubrikEN", ""),
                    "category": item.get("Kategori", ""),
                    "timestamp": item.get("Tidstampel", ""),
                },
            )
