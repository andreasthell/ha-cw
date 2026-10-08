"""CheckWatt binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CheckwattCoordinator, activation_attributes
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CheckWatt binary sensors from a config entry."""
    coordinator: CheckwattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CheckwattMfrrActivationSensor(coordinator)])


class CheckwattMfrrActivationSensor(CoordinatorEntity[CheckwattCoordinator], BinarySensorEntity):
    """On while the battery is activated for mFRR (up or down regulation).

    Attributes describe the ongoing activation, or the latest one when off.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "mfrr_activation"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: CheckwattCoordinator) -> None:
        super().__init__(coordinator)
        serial = coordinator.data.get("rpi_serial", "unknown")
        self._attr_unique_id = f"{serial}_mfrr_activation"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.is_on is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("mfrr_activation_active")

    @property
    def extra_state_attributes(self) -> dict | None:
        activation = self.coordinator.data.get("mfrr_activation")
        return activation_attributes(activation) if activation else None
