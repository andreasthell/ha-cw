"""Tests for the spot price slot selection logic."""

from datetime import datetime

from custom_components.checkwatt import _select_spot_price

PRICES = [
    {"Value": 1.10, "Date": "2026-06-08T00:00:00.000"},
    {"Value": 1.20, "Date": "2026-06-08T00:15:00.000"},
    {"Value": 1.30, "Date": "2026-06-08T00:30:00.000"},
    {"Value": 1.40, "Date": "2026-06-08T00:45:00.000"},
]


class TestSelectSpotPrice:
    def test_empty_list(self):
        assert _select_spot_price([], datetime(2026, 6, 8, 12, 0)) is None

    def test_before_first_slot(self):
        assert _select_spot_price(PRICES, datetime(2026, 6, 7, 23, 59)) is None

    def test_exact_slot_start(self):
        assert _select_spot_price(PRICES, datetime(2026, 6, 8, 0, 15)) == 1.20

    def test_mid_slot(self):
        assert _select_spot_price(PRICES, datetime(2026, 6, 8, 0, 37)) == 1.30

    def test_after_last_slot(self):
        assert _select_spot_price(PRICES, datetime(2026, 6, 8, 23, 0)) == 1.40

    def test_malformed_entries_skipped(self):
        prices = [
            {"Value": 1.0},  # no Date
            {"Value": 2.0, "Date": "not-a-date"},
            {"Value": 3.0, "Date": None},
            {"Value": 4.0, "Date": "2026-06-08T00:00:00.000"},
        ]
        assert _select_spot_price(prices, datetime(2026, 6, 8, 0, 5)) == 4.0
