"""Fixtures for tests that run the integration in a real Home Assistant.

These need pytest-homeassistant-custom-component (requirements_test_ha.txt)
and cannot share a run with tests/, which stubs out homeassistant:

    pytest tests_ha -o asyncio_mode=auto
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.checkwatt  # noqa: F401  (lets patch() resolve the module)

SERIAL = "aabbccddeeff"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeClient:
    """Serves one site; tests change the attributes between refreshes."""

    def __init__(self) -> None:
        self.test_status = "Activated"
        self.logbook = "[ mfrrup ACTIVATED ] user 2026-09-04 00:02:54 API-BACKEND"
        self.schedule: dict = {"MfrrUpActivation": None, "MfrrDownActivation": None}
        self.monthly_revenue: list[dict] = []

    async def ensure_authenticated(self):
        pass

    async def get_customer_details(self):
        meter = {"InstallationType": "SoC", "RpiSerial": SERIAL, "Logbook": self.logbook}
        return {"Meter": [meter]}

    async def get_site_id_by_serial(self, serial):
        return 12345

    async def get_energy_flow(self):
        return {"SolarIds": [1], "SolarNow": 0.0, "BatterySoC": 85.0}

    async def get_site_statuses(self, serial):
        return [{"TestInfo": {"Latest": self.test_status}, "Mba": "SE4", "DisplayName": "Site"}]

    async def get_revenue(self, site_id, from_date, to_date, resolution="day"):
        return {"Revenue": self.monthly_revenue if resolution == "month" else []}

    async def get_price_zone(self):
        return "SE4"

    async def get_spot_prices(self, zone, from_date, to_date, site_id):
        return {"Prices": []}

    async def get_energy_totals(self, meter_ids):
        return {"Meters": []}

    async def get_connection_status(self, site_id):
        return {}

    async def get_news(self):
        return []

    async def get_activation_schedule(self):
        return self.schedule


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
async def entry(hass: HomeAssistant, client: FakeClient) -> MockConfigEntry:
    """Set up the integration with *client* and return its config entry."""
    entry = MockConfigEntry(domain="checkwatt", data={"username": "u", "password": "p"})
    entry.add_to_hass(hass)
    with patch("custom_components.checkwatt.CheckwattApiClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Run one coordinator refresh with every slow update due."""
    coordinator = hass.data["checkwatt"][entry.entry_id]
    for status in coordinator._update_status.values():
        status["next_attempt"] = datetime.min.replace(tzinfo=UTC)
    await coordinator.async_refresh()
    await hass.async_block_till_done()


def entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    entity = er.async_get(hass).async_get_entity_id(platform, "checkwatt", f"{SERIAL}_{key}")
    assert entity is not None, f"no {platform} entity for {key}"
    return entity
