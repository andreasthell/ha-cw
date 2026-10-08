"""Run the integration in a real Home Assistant and check its entities."""

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import FakeClient, entity_id, refresh

EVENTS = ("cm10_test_status", "logbook_event", "mfrr_activation_event")


async def test_setup_without_errors(hass: HomeAssistant, entry, caplog) -> None:
    assert entry.state.value == "loaded"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == []
    assert hass.states.get(entity_id(hass, "sensor", "battery_soc_pct")).state == "85.0"


async def test_events_are_unknown_until_something_happens(hass: HomeAssistant, entry) -> None:
    await refresh(hass, entry)
    for key in EVENTS:
        assert hass.states.get(entity_id(hass, "event", key)).state == STATE_UNKNOWN
    assert hass.states.get(entity_id(hass, "binary_sensor", "mfrr_activation")).state == STATE_OFF


async def test_events_fire(hass: HomeAssistant, entry, client: FakeClient) -> None:
    client.test_status = "Deactivated"
    client.logbook = "[ mfrrup DEACTIVATE ] user 2026-10-08 15:00:00 API-BACKEND\n" + client.logbook
    start = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=2)
    client.schedule = {
        "MfrrUpActivation": [
            {
                "Time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "EndTime": (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Power": 5614.48,
                "RampUpTime": 600,
                "RampDownTime": 600,
            }
        ]
    }
    await refresh(hass, entry)

    cm10 = hass.states.get(entity_id(hass, "event", "cm10_test_status"))
    assert cm10.attributes["event_type"] == "deactivated"
    assert cm10.attributes["previous_status"] == "Activated"

    logbook = hass.states.get(entity_id(hass, "event", "logbook_event"))
    assert logbook.attributes["event_type"] == "deactivated"
    assert logbook.attributes["timestamp"] == "2026-10-08 15:00:00"

    mfrr = hass.states.get(entity_id(hass, "event", "mfrr_activation_event"))
    assert mfrr.attributes["event_type"] == "up"
    assert mfrr.attributes["power_w"] == 5614
    assert mfrr.attributes["start"] == start

    active = hass.states.get(entity_id(hass, "binary_sensor", "mfrr_activation"))
    assert active.state == STATE_ON
    assert active.attributes["direction"] == "up"

    # The same activation in the next response is not a new event.
    fired_at = mfrr.state
    await refresh(hass, entry)
    assert hass.states.get(entity_id(hass, "event", "mfrr_activation_event")).state == fired_at


async def test_last_event_survives_reload(hass: HomeAssistant, entry, client: FakeClient) -> None:
    client.test_status = "Deactivated"
    await refresh(hass, entry)
    cm10 = entity_id(hass, "event", "cm10_test_status")
    fired_at = hass.states.get(cm10).state
    assert fired_at != STATE_UNKNOWN

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(cm10)
    assert state.state == fired_at
    assert state.attributes["event_type"] == "deactivated"


async def test_total_revenue(hass: HomeAssistant, entry, client: FakeClient) -> None:
    client.monthly_revenue = [
        {"ServiceName": "FCR-D", "Date": "2026-02-01", "NetRevenue": 297.38},
        {"ServiceName": "mFRR CM", "Date": "2026-10-01", "NetRevenue": 470.5},
        {"ServiceName": "mFRR EAM", "Date": "2026-10-01", "NetRevenue": 23.76},
    ]
    await refresh(hass, entry)
    state = hass.states.get(entity_id(hass, "sensor", "total_revenue_sek"))
    assert float(state.state) == 791.64
    assert state.attributes["unit_of_measurement"] == "SEK"
    assert state.attributes["by_service"] == {
        "FCR-D": 297.38,
        "mFRR CM": 470.5,
        "mFRR EAM": 23.76,
    }


async def test_unload(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "not_loaded"
