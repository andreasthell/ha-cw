"""Tests for CheckwattCoordinator update cycles, driven by a fake API client."""

import asyncio

from custom_components.checkwatt import CheckwattCoordinator

_SLOW_UPDATE_ATTRS = (
    "_last_revenue_update",
    "_last_price_update",
    "_last_energy_update",
    "_last_logbook_update",
    "_last_diag_update",
    "_last_news_update",
)


class FakeClient:
    """Serves a single site; tests change the attributes between cycles."""

    def __init__(self):
        self.test_status: str | None = "Activated"
        self.revenue: list[dict] = []
        self.meters: list[dict] = [{"Measurements": [{"Value": 5_000_000.0}]}]

    async def ensure_authenticated(self):
        pass

    async def get_customer_details(self):
        return {"Meter": [{"InstallationType": "SoC", "RpiSerial": "AABBCCDDEEFF"}]}

    async def get_site_id_by_serial(self, serial):
        return 12345

    async def get_energy_flow(self):
        return {"SolarIds": [100002]}

    async def get_site_statuses(self, serial):
        if self.test_status is None:
            return []
        return [{"TestInfo": {"Latest": self.test_status}}]

    async def get_revenue(self, site_id, from_date, to_date):
        return {"Revenue": self.revenue}

    async def get_price_zone(self):
        return "SE4"

    async def get_spot_prices(self, zone, from_date, to_date):
        return {"Prices": []}

    async def get_energy_totals(self, meter_ids):
        return {"Meters": self.meters}

    async def get_connection_status(self, site_id):
        return {}

    async def get_news(self):
        return []


def _coordinator() -> tuple[CheckwattCoordinator, FakeClient]:
    client = FakeClient()
    return CheckwattCoordinator(None, client, None), client


def _refresh(coordinator: CheckwattCoordinator) -> dict:
    """Run one update cycle with every slow update due, storing data like HA does."""
    for attr in _SLOW_UPDATE_ATTRS:
        setattr(coordinator, attr, None)
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
