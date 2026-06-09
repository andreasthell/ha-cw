"""Tests for the logbook new-entry detection logic in the coordinator."""


def _new_entries(all_entries: list[dict], last_ts: str | None) -> list[dict]:
    """Mirror the filtering logic from CheckwattCoordinator._update_logbook."""
    if last_ts is None:
        return []
    return [e for e in all_entries if e.get("timestamp") and e["timestamp"] > last_ts]


class TestLogbookDiff:
    def test_no_new_entries(self):
        entries = [
            {"event": "Activated", "timestamp": "2024-03-01 10:00:00", "detail": ""},
        ]
        assert _new_entries(entries, "2024-03-01 10:00:00") == []

    def test_one_new_entry(self):
        entries = [
            {"event": "Deactivated", "timestamp": "2024-03-02 08:00:00", "detail": ""},
            {"event": "Activated", "timestamp": "2024-03-01 10:00:00", "detail": ""},
        ]
        result = _new_entries(entries, "2024-03-01 10:00:00")
        assert len(result) == 1
        assert result[0]["timestamp"] == "2024-03-02 08:00:00"

    def test_multiple_new_entries(self):
        entries = [
            {"event": "C", "timestamp": "2024-03-03 00:00:00", "detail": ""},
            {"event": "B", "timestamp": "2024-03-02 00:00:00", "detail": ""},
            {"event": "A", "timestamp": "2024-03-01 00:00:00", "detail": ""},
        ]
        result = _new_entries(entries, "2024-03-01 00:00:00")
        assert len(result) == 2
        # Entries returned newest-first (as they come from the API).
        assert result[0]["event"] == "C"
        assert result[1]["event"] == "B"

    def test_oldest_first_after_reverse(self):
        """Coordinator reverses the list before putting it in data."""
        entries = [
            {"event": "C", "timestamp": "2024-03-03 00:00:00", "detail": ""},
            {"event": "B", "timestamp": "2024-03-02 00:00:00", "detail": ""},
            {"event": "A", "timestamp": "2024-03-01 00:00:00", "detail": ""},
        ]
        new = _new_entries(entries, "2024-03-01 00:00:00")
        oldest_first = list(reversed(new))
        assert oldest_first[0]["event"] == "B"
        assert oldest_first[1]["event"] == "C"

    def test_last_ts_none_fires_nothing(self):
        """When last_ts is None (bootstrap), no events should be fired."""
        entries = [
            {"event": "Activated", "timestamp": "2024-03-01 10:00:00", "detail": ""},
        ]
        assert _new_entries(entries, None) == []

    def test_entry_without_timestamp_is_ignored(self):
        entries = [
            {"event": "Activated", "timestamp": None, "detail": ""},
            {"event": "Old", "timestamp": "2024-03-01 10:00:00", "detail": ""},
        ]
        result = _new_entries(entries, "2024-03-01 10:00:00")
        assert result == []
