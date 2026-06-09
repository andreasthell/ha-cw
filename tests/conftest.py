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
    ),
    SensorEntity=object,
    SensorEntityDescription=_SensorEntityDescription,
    SensorStateClass=_enum_stub("SensorStateClass", "MEASUREMENT", "TOTAL", "TOTAL_INCREASING"),
)
_stub("homeassistant.components.event", EventEntity=object)
_stub(
    "homeassistant.const",
    PERCENTAGE="PERCENTAGE",
    UnitOfEnergy=type("UnitOfEnergy", (), {"KILO_WATT_HOUR": "kWh"}),
    UnitOfPower=type("UnitOfPower", (), {"WATT": "W"}),
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


_stub(
    "homeassistant.helpers.update_coordinator",
    CoordinatorEntity=_Generic,
    DataUpdateCoordinator=_Generic,
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
