"""Tests for the event entities and their helper functions."""

from types import SimpleNamespace

from custom_components.checkwatt.event import (
    CheckwattCm10StatusEvent,
    CheckwattLogbookEvent,
    CheckwattNewsEvent,
    _map_cm10_event_type,
    _map_logbook_event_type,
    _map_news_event_type,
)


def _entity(cls):
    coordinator = SimpleNamespace(data={"rpi_serial": "aabbccddeeff"}, last_update_success=True)
    return cls(coordinator)


def _update(entity, success: bool = True, **data) -> None:
    """Deliver one coordinator refresh to *entity*."""
    entity.coordinator.data = {"rpi_serial": "aabbccddeeff", **data}
    entity.coordinator.last_update_success = success
    entity._handle_coordinator_update()


class TestEventPublishing:
    def test_every_logbook_entry_is_published(self):
        entity = _entity(CheckwattLogbookEvent)
        entries = [
            {"event": "mfrrup ACTIVATED", "timestamp": "2026-09-01 10:00:00", "detail": ""},
            {"event": "mfrrup DEACTIVATE", "timestamp": "2026-09-01 10:15:00", "detail": ""},
            {"event": "FAIL", "timestamp": "2026-09-01 10:30:00", "detail": "timeout"},
        ]
        _update(entity, new_logbook_entries=entries)
        assert [t for t, _ in entity.published_events] == ["activated", "deactivated", "failed"]
        assert [a["timestamp"] for _, a in entity.published_events] == [
            "2026-09-01 10:00:00",
            "2026-09-01 10:15:00",
            "2026-09-01 10:30:00",
        ]

    def test_every_news_item_is_published(self):
        entity = _entity(CheckwattNewsEvent)
        items = [
            {"Rubrik": "Första", "Kategori": "Nyheter", "Tidstampel": "2026-09-01"},
            {"Rubrik": "Andra", "Kategori": "Uppdatering", "Tidstampel": "2026-09-02"},
        ]
        _update(entity, new_news_items=items)
        assert [(t, a["title"]) for t, a in entity.published_events] == [
            ("news", "Första"),
            ("update", "Andra"),
        ]

    def test_cm10_change_is_published(self):
        entity = _entity(CheckwattCm10StatusEvent)
        _update(
            entity,
            cm10_status_changed=True,
            cm10_status_prev="Activated",
            test_info={"Latest": "Deactivated", "Result": None, "FailedInARow": 0},
        )
        assert len(entity.published_events) == 1
        event_type, attributes = entity.published_events[0]
        assert event_type == "deactivated"
        assert attributes["previous_status"] == "Activated"

    def test_cycle_without_new_events_publishes_nothing(self):
        entity = _entity(CheckwattLogbookEvent)
        _update(entity, new_logbook_entries=[])
        assert entity.published_events == []

    def test_failed_refresh_publishes_nothing(self):
        entity = _entity(CheckwattLogbookEvent)
        entries = [{"event": "ACTIVATED", "timestamp": "2026-09-01 10:00:00", "detail": ""}]
        _update(entity, success=False, new_logbook_entries=entries)
        assert entity.published_events == []


class TestMapCm10EventType:
    def test_activated(self):
        assert _map_cm10_event_type("Activated") == "activated"
        assert _map_cm10_event_type("ACTIVATED") == "activated"

    def test_deactivated(self):
        assert _map_cm10_event_type("Deactivated") == "deactivated"
        assert _map_cm10_event_type("DEACTIVATED") == "deactivated"

    def test_failed(self):
        assert _map_cm10_event_type("Failed test") == "failed"
        assert _map_cm10_event_type("FAIL") == "failed"

    def test_other_string(self):
        assert _map_cm10_event_type("SomeUnknownStatus") == "other"

    def test_none(self):
        assert _map_cm10_event_type(None) == "other"

    def test_empty_string(self):
        assert _map_cm10_event_type("") == "other"


class TestMapLogbookEventType:
    def test_activated(self):
        assert _map_logbook_event_type("Activated") == "activated"
        assert _map_logbook_event_type("[ACTIVATED]") == "activated"

    def test_deactivated(self):
        assert _map_logbook_event_type("Deactivated") == "deactivated"
        assert _map_logbook_event_type("DEACTIVATE") == "deactivated"

    def test_failed(self):
        assert _map_logbook_event_type("Failed") == "failed"
        assert _map_logbook_event_type("FAIL reason") == "failed"

    def test_adjusted(self):
        assert _map_logbook_event_type("Adjusted") == "adjusted"
        assert _map_logbook_event_type("ADJUST power") == "adjusted"

    def test_other(self):
        assert _map_logbook_event_type("Unknown event") == "other"
        assert _map_logbook_event_type("") == "other"


class TestMapNewsEventType:
    def test_nyheter(self):
        assert _map_news_event_type("Nyheter") == "news"
        assert _map_news_event_type("nyheter") == "news"

    def test_uppdatering(self):
        assert _map_news_event_type("Uppdatering") == "update"
        assert _map_news_event_type("UPPDATERING") == "update"

    def test_other(self):
        assert _map_news_event_type("Okänd kategori") == "other"
        assert _map_news_event_type("") == "other"
