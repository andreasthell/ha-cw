"""Shared pytest configuration — stubs out homeassistant so real modules can import."""

import sys
import types
from pathlib import Path

# Add the project root so `custom_components.checkwatt.*` can be imported directly.
sys.path.insert(0, str(Path(__file__).parent.parent))


def _stub(name: str, **attrs):
    """Create or update a stub module in sys.modules."""
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for k, v in attrs.items():
        setattr(mod, k, v)
    # Ensure parent packages are also registered.
    parts = name.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        sys.modules.setdefault(parent, types.ModuleType(parent))
    return mod


import dataclasses  # noqa: E402


# A minimal SensorEntityDescription that survives @dataclass(frozen=True, kw_only=True).
# Must include all fields that CheckwattSensorDescription or its instances use.
@dataclasses.dataclass(frozen=True, kw_only=True)
class _SensorEntityDescription:
    key: str = ""
    translation_key: str | None = None
    device_class: object = None
    state_class: object = None
    native_unit_of_measurement: str | None = None
    suggested_display_precision: int | None = None
    icon: str | None = None


_stub("homeassistant")
_stub("homeassistant.components")


def _enum_stub(name: str, *values: str):
    """Create a class whose attributes return the attribute name as a string."""
    attrs = {v: v for v in values}
    attrs["__class_getitem__"] = classmethod(lambda cls, item: cls)
    return type(name, (), attrs)


_stub(
    "homeassistant.components.sensor",
    SensorDeviceClass=_enum_stub(
        "SensorDeviceClass",
        "POWER",
        "BATTERY",
        "MONETARY",
        "ENERGY",
        "TIMESTAMP",
        "TEMPERATURE",
    ),
    SensorEntity=object,
    SensorEntityDescription=_SensorEntityDescription,
    SensorStateClass=_enum_stub("SensorStateClass", "MEASUREMENT", "TOTAL", "TOTAL_INCREASING"),
)


class _EventEntity:
    """Mirrors HA: _trigger_event() only stores the event; it becomes a state
    change (what automations see) only when async_write_ha_state() runs."""

    def __init__(self):
        self.published_events: list[tuple[str, dict | None]] = []
        self._pending_event: tuple[str, dict | None] | None = None

    def _trigger_event(self, event_type, event_attributes=None):
        if event_type not in self._attr_event_types:
            raise ValueError(f"Invalid event type {event_type}")
        self._pending_event = (event_type, event_attributes)

    def async_write_ha_state(self):
        if self._pending_event is not None:
            self.published_events.append(self._pending_event)
            self._pending_event = None


_stub("homeassistant.components.event", EventEntity=_EventEntity)
_stub(
    "homeassistant.const",
    PERCENTAGE="PERCENTAGE",
    UnitOfEnergy=type("UnitOfEnergy", (), {"KILO_WATT_HOUR": "kWh"}),
    UnitOfPower=type("UnitOfPower", (), {"WATT": "W", "KILO_WATT": "kW"}),
    UnitOfTemperature=type("UnitOfTemperature", (), {"CELSIUS": "°C"}),
    CONF_USERNAME="username",
    CONF_PASSWORD="password",
    Platform=type("Platform", (), {"SENSOR": "sensor", "EVENT": "event"}),
)
_stub("homeassistant.core", HomeAssistant=object)
_stub("homeassistant.helpers")
_stub("homeassistant.helpers.device_registry", DeviceInfo=dict)
_stub("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
_stub("homeassistant.helpers.typing", StateType=object)


class _Generic:
    def __class_getitem__(cls, item):
        return cls


class _DataUpdateCoordinator(_Generic):
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.data = None


class _CoordinatorEntity(_Generic):
    def __init__(self, coordinator):
        super().__init__()
        self.coordinator = coordinator

    def _handle_coordinator_update(self):
        self.async_write_ha_state()


_stub(
    "homeassistant.helpers.update_coordinator",
    CoordinatorEntity=_CoordinatorEntity,
    DataUpdateCoordinator=_DataUpdateCoordinator,
    UpdateFailed=Exception,
)
_stub(
    "homeassistant.helpers.aiohttp_client",
    async_get_clientsession=lambda hass: None,
    async_create_clientsession=lambda hass, **kw: None,
)
_stub(
    "homeassistant.config_entries",
    ConfigEntry=object,
    ConfigFlow=object,
    ConfigFlowResult=object,
    OptionsFlow=object,
)
_stub("homeassistant.exceptions", ConfigEntryAuthFailed=Exception)

# Third-party stubs
_stub(
    "aiohttp",
    ClientError=Exception,
    ClientResponseError=Exception,
    ClientSession=object,
    ClientTimeout=lambda **kw: kw,
)
