"""Tests for event entity helper functions."""

from custom_components.checkwatt.event import _map_cm10_event_type, _map_logbook_event_type


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
