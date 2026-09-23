"""Tests for CheckwattCoordinator update cycles, driven by a fake API client."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import custom_components.checkwatt as checkwatt
from custom_components.checkwatt import CheckwattCoordinator


class FakeClient:
    """Serves a single site; tests change the attributes between cycles."""

    def __init__(self):
        self.test_status: str | None = "Activated"
        self.revenue: list[dict] = []
        self.meters: list[dict] = [{"Measurements": [{"Value": 5_000_000.0}]}]
        self.logbook = ""
        self.connection_status: dict = {}
        self.news_error: Exception | None = None
        self.revenue_dates: list[tuple[str, str]] = []

    async def ensure_authenticated(self):
        pass

    async def get_customer_details(self):
        meter = {"InstallationType": "SoC", "RpiSerial": "AABBCCDDEEFF", "Logbook": self.logbook}
        return {"Meter": [meter]}

    async def get_site_id_by_serial(self, serial):
        return 12345

    async def get_energy_flow(self):
        return {"SolarIds": [100002]}

    async def get_site_statuses(self, serial):
        if self.test_status is None:
            return []
        return [{"TestInfo": {"Latest": self.test_status}}]

    async def get_revenue(self, site_id, from_date, to_date):
        self.revenue_dates.append((from_date, to_date))
        return {"Revenue": self.revenue}

    async def get_price_zone(self):
        return "SE4"

    async def get_spot_prices(self, zone, from_date, to_date):
        return {"Prices": []}

    async def get_energy_totals(self, meter_ids):
        return {"Meters": self.meters}

    async def get_connection_status(self, site_id):
        return self.connection_status

    async def get_news(self):
        if self.news_error:
            raise self.news_error
        return []


def _coordinator() -> tuple[CheckwattCoordinator, FakeClient]:
    client = FakeClient()
    return CheckwattCoordinator(None, client, None), client


def _refresh(coordinator: CheckwattCoordinator) -> dict:
    """Run one update cycle with every slow update due, storing data like HA does."""
    coordinator._next_update.clear()
    coordinator.data = asyncio.run(coordinator._async_update_data())
    return coordinator.data


class TestCm10StatusChange:
    def test_first_cycle_fires_nothing(self):
        coordinator, _ = _coordinator()
        assert _refresh(coordinator)["cm10_status_changed"] is False

    def test_transition_fires_once(self):
        coordinator, client = _coordinator()
        _refresh(coordinator)
        client.test_status = "Deactivated"
        data = _refresh(coordinator)
        assert data["cm10_status_changed"] is True
        assert data["cm10_status_prev"] == "Activated"
        assert _refresh(coordinator)["cm10_status_changed"] is False

    def test_missing_status_does_not_fire(self):
        coordinator, client = _coordinator()
        _refresh(coordinator)
        client.test_status = None  # /site/Statuses returned an empty list
        for _ in range(3):
            assert _refresh(coordinator)["cm10_status_changed"] is False
        client.test_status = "Activated"  # back, unchanged
        assert _refresh(coordinator)["cm10_status_changed"] is False


class TestTodayRevenue:
    def test_no_entries_yet_today_is_zero(self):
        coordinator, client = _coordinator()
        client.revenue = [{"ServiceName": "mFRR CM", "NetRevenue": 84.48, "Estimate": True}]
        assert _refresh(coordinator)["today_revenue_sek"] == 84.48
        client.revenue = []  # new day: the API omits days without data
        data = _refresh(coordinator)
        assert data["today_revenue_sek"] == 0
        assert data["today_revenue_estimate"] is False

    def test_service_name_kept_when_no_entries(self):
        coordinator, client = _coordinator()
        client.revenue = [{"ServiceName": "mFRR CM", "NetRevenue": 84.48}]
        _refresh(coordinator)
        client.revenue = []
        assert _refresh(coordinator)["today_service_name"] == "mFRR CM"

    def test_entries_for_several_services_are_summed(self):
        coordinator, client = _coordinator()
        client.revenue = [
            {"ServiceName": "mFRR CM", "NetRevenue": 10.5, "Estimate": False},
            {"ServiceName": "FCR-D", "NetRevenue": 4.25, "Estimate": True},
        ]
        data = _refresh(coordinator)
        assert data["today_revenue_sek"] == 14.75
        assert data["today_revenue_estimate"] is True
        assert data["today_service_name"] == "mFRR CM, FCR-D"

    def test_null_net_revenue_counts_as_zero(self):
        coordinator, client = _coordinator()
        client.revenue = [{"ServiceName": "FCR-D", "NetRevenue": None}]
        assert _refresh(coordinator)["today_revenue_sek"] == 0


class TestEnergyTotals:
    def test_total_converted_to_kwh(self):
        coordinator, _ = _coordinator()
        assert _refresh(coordinator)["total_solar_kwh"] == 5000.0

    def test_empty_response_keeps_previous_total(self):
        coordinator, client = _coordinator()
        _refresh(coordinator)
        client.meters = []  # 200 OK, but no data
        assert _refresh(coordinator)["total_solar_kwh"] == 5000.0

    def test_decrease_is_ignored(self):
        coordinator, client = _coordinator()
        _refresh(coordinator)
        client.meters = [{"Measurements": [{"Value": 4_000_000.0}]}]  # partial response
        assert _refresh(coordinator)["total_solar_kwh"] == 5000.0
        client.meters = [{"Measurements": [{"Value": 5_000_500.0}]}]
        assert _refresh(coordinator)["total_solar_kwh"] == 5000.5

    def test_empty_first_response_publishes_nothing(self):
        coordinator, client = _coordinator()
        client.meters = [{"Measurements": []}]
        assert _refresh(coordinator)["total_solar_kwh"] is None


class TestSwedishDates:
    def test_revenue_uses_swedish_date(self, monkeypatch):
        # 22:30 UTC on 30 Sep is already 1 Oct in Sweden.
        frozen = datetime(2026, 9, 30, 22, 30, tzinfo=UTC)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

        monkeypatch.setattr(checkwatt, "datetime", FrozenDatetime)
        coordinator, client = _coordinator()
        _refresh(coordinator)
        assert client.revenue_dates == [
            ("2026-10-01", "2026-10-01"),  # today
            ("2026-10-01", "2026-10-01"),  # month to date
        ]


class TestSlowUpdateRetry:
    def test_failed_update_is_retried_soon(self):
        coordinator, client = _coordinator()
        client.news_error = ConnectionError("news host down")
        before = datetime.now(UTC)
        _refresh(coordinator)
        assert coordinator._next_update["news"] <= before + timedelta(minutes=6)

    def test_successful_update_waits_full_interval(self):
        coordinator, _ = _coordinator()
        before = datetime.now(UTC)
        _refresh(coordinator)
        assert coordinator._next_update["news"] >= before + timedelta(hours=4)


class TestLogbookSeeding:
    def test_newest_line_without_timestamp_still_seeds(self):
        coordinator, client = _coordinator()
        client.logbook = (
            "[Note] manual comment without a date\n"
            "[mfrrup ACTIVATED] 2026-09-01 10:00:00 API-BACKEND\n"
        )
        _refresh(coordinator)
        assert coordinator._last_logbook_ts == "2026-09-01 10:00:00"
        client.logbook = "[mfrrup DEACTIVATE] 2026-09-01 11:00:00 API-BACKEND\n" + client.logbook
        data = _refresh(coordinator)
        assert [e["timestamp"] for e in data["new_logbook_entries"]] == ["2026-09-01 11:00:00"]


def _connection_status(age: timedelta) -> dict:
    reported = (datetime.now(UTC) - age).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = {"hello_eth0": True, "uptime_s": 100}
    return {"Current": {"Timestamp": reported, "Blob": json.dumps(blob)}}


class TestDiagnostics:
    def test_recent_report_is_used(self):
        coordinator, client = _coordinator()
        client.connection_status = _connection_status(timedelta(hours=1))
        assert _refresh(coordinator)["internet_connection"] == "Network cable (LAN1)"

    def test_stale_report_is_unknown(self):
        coordinator, client = _coordinator()
        client.connection_status = _connection_status(timedelta(minutes=10))
        _refresh(coordinator)
        client.connection_status = _connection_status(timedelta(hours=5))
        data = _refresh(coordinator)
        assert data["internet_connection"] is None
        assert data["cm10_uptime_s"] is None

    def test_missing_report_is_unknown(self):
        coordinator, client = _coordinator()
        client.connection_status = _connection_status(timedelta(minutes=10))
        _refresh(coordinator)
        client.connection_status = {"Current": None}
        assert _refresh(coordinator)["internet_connection"] is None
