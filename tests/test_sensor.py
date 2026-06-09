"""Tests for sensor helper functions."""

from datetime import UTC

from custom_components.checkwatt.sensor import (
    _friendly_event,
    _logbook_state,
    _op_pref_label,
    _parse_dt,
    _parse_logbook,
)


class TestParseLogbook:
    def test_empty_returns_none_and_empty_list(self):
        assert _parse_logbook(None) == (None, [])
        assert _parse_logbook("") == (None, [])

    def test_single_entry(self):
        raw = "[Activated] 2024-03-01 10:00:00 API-BACKEND"
        latest, entries = _parse_logbook(raw)
        assert latest == "Activated"
        assert len(entries) == 1
        assert entries[0]["event"] == "Activated"
        assert entries[0]["timestamp"] == "2024-03-01 10:00:00"

    def test_multiple_entries_newest_first(self):
        raw = (
            "[Activated] 2024-03-02 12:00:00 API-BACKEND\n"
            "[Deactivated] 2024-03-01 08:00:00 API-BACKEND\n"
        )
        latest, entries = _parse_logbook(raw)
        assert latest == "Activated"
        assert entries[0]["timestamp"] == "2024-03-02 12:00:00"
        assert entries[1]["timestamp"] == "2024-03-01 08:00:00"

    def test_capped_at_25(self):
        lines = "\n".join(f"[Event{i}] 2024-01-{i:02d} 00:00:00 API-BACKEND" for i in range(1, 35))
        _, entries = _parse_logbook(lines)
        assert len(entries) == 25

    def test_entry_without_timestamp(self):
        raw = "[Failed] some text without a date"
        _, entries = _parse_logbook(raw)
        assert entries[0]["timestamp"] is None
        assert entries[0]["event"] == "Failed"

    def test_multiple_tags_on_one_line(self):
        raw = "[Activated] [ExtraTag] 2024-05-01 09:00:00 API-BACKEND"
        _, entries = _parse_logbook(raw)
        assert "Activated" in entries[0]["event"]
        assert "ExtraTag" in entries[0]["event"]

    def test_api_backend_suffix_stripped_correctly(self):
        # rstrip("API-BACKEND") would also strip trailing 'G', 'N', 'E' etc.
        # The regex approach must only remove the literal suffix.
        raw = "[Activated] 2024-03-01 10:00:00 some detail ending in G API-BACKEND"
        _, entries = _parse_logbook(raw)
        assert entries[0]["detail"].endswith("G")

    def test_logbook_raw_capped_at_max_bytes(self):
        from custom_components.checkwatt.sensor import _LOGBOOK_MAX_BYTES

        oversized = "[Event] 2024-01-01 00:00:00\n" * 10_000
        assert len(oversized) > _LOGBOOK_MAX_BYTES
        _, entries = _parse_logbook(oversized)
        assert len(entries) == 25  # still capped at 25 entries


class TestParseDt:
    def test_none_input(self):
        assert _parse_dt(None) is None

    def test_empty_string(self):
        assert _parse_dt("") is None

    def test_valid_iso(self):
        dt = _parse_dt("2024-03-01T10:00:00Z")
        assert dt is not None
        assert dt.tzinfo == UTC

    def test_invalid_string(self):
        assert _parse_dt("not-a-date") is None


class TestOpPrefLabel:
    def test_known_codes(self):
        assert _op_pref_label("co") == "Currently Optimized"
        assert _op_pref_label("sc") == "Self Consumption"

    def test_unknown_code_passthrough(self):
        assert _op_pref_label("xx") == "xx"

    def test_none(self):
        assert _op_pref_label(None) is None


class TestFriendlyEvent:
    def test_known_mappings(self):
        assert _friendly_event("mfrrup DEACTIVATE") == "Deactivated"
        assert _friendly_event("mfrrup ACTIVATED") == "Activated"
        assert _friendly_event("FAIL reason") == "Failed"
        assert _friendly_event("ADJUST power") == "Adjusted"

    def test_unknown_passthrough(self):
        assert _friendly_event("SOME UNKNOWN EVENT") == "SOME UNKNOWN EVENT"

    def test_deactivate_before_activated(self):
        # "DEACTIVATE" contains neither "ACTIVATED" first — mapping order matters.
        assert _friendly_event("mfrrup DEACTIVATE") == "Deactivated"
        assert _friendly_event("mfrrup ACTIVATED") == "Activated"


class TestLogbookState:
    def test_none_input(self):
        assert _logbook_state(None) is None

    def test_empty_input(self):
        assert _logbook_state("") is None

    def test_formats_time_and_event(self):
        raw = "[mfrrup ACTIVATED] 2024-03-01 18:12:34 API-BACKEND"
        state = _logbook_state(raw)
        assert state == "18:12 · Activated"

    def test_unknown_event_shown_as_is(self):
        raw = "[WEIRD EVENT] 2024-03-01 09:05:00 API-BACKEND"
        state = _logbook_state(raw)
        assert state == "09:05 · WEIRD EVENT"

    def test_no_timestamp_shows_question_mark(self):
        raw = "[mfrrup ACTIVATED] no timestamp here"
        state = _logbook_state(raw)
        assert "?" in state
