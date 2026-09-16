"""Tests for connectionStatus diagnostics blob parsing."""

from custom_components.checkwatt import _parse_diag_blob


def _blob(**overrides) -> dict:
    """A realistic Current.Blob dict, shaped like the 2026-09 API response."""
    blob = {
        "eth": {"eth0": {"rx_packets": 4527}, "eth1": {"rx_packets": 61803}},
        "topics": {
            "ems/inverter_stat": {
                "goodwe": [
                    {
                        "id": "192.168.5.128",
                        "soc": 85.0,
                        "model": "GW10KN-ET ",
                        "temp_h": 36.4,
                        "temp_l": 20.8,
                        "pv_power": 0.0,
                        "battery_power": -12.0,
                    }
                ]
            },
            "ems/datastream_energyPv": 0.0,
        },
        "uptime_s": 1114187,
        "hello_eth0": True,
        "modem_stat": {"ts": "2026-09-16 04:05:04", "status": "modem"},
        "default_route": ["ppp0", "eth0"],
    }
    blob.update(overrides)
    return blob


class TestParseDiagBlob:
    def test_battery_temperatures(self):
        result = _parse_diag_blob(_blob())
        assert result["battery_temp_high_c"] == 36.4
        assert result["battery_temp_low_c"] == 20.8

    def test_multiple_inverters_take_extremes(self):
        blob = _blob()
        blob["topics"]["ems/inverter_stat"]["goodwe"].append({"temp_h": 40.1, "temp_l": 25.0})
        result = _parse_diag_blob(blob)
        assert result["battery_temp_high_c"] == 40.1
        assert result["battery_temp_low_c"] == 20.8

    def test_no_inverter_stats(self):
        result = _parse_diag_blob(_blob(topics={}))
        assert result["battery_temp_high_c"] is None
        assert result["battery_temp_low_c"] is None

    def test_missing_temps_ignored(self):
        blob = _blob()
        blob["topics"]["ems/inverter_stat"]["goodwe"] = [{"temp_h": None, "temp_l": None}]
        result = _parse_diag_blob(blob)
        assert result["battery_temp_high_c"] is None
        assert result["battery_temp_low_c"] is None

    def test_lan_connected(self):
        result = _parse_diag_blob(_blob())
        assert result["internet_connection"] == "Network cable (LAN1)"

    def test_modem_fallback(self):
        result = _parse_diag_blob(_blob(hello_eth0=False))
        assert result["internet_connection"] == "Mobile internet (4G)"

    def test_no_internet(self):
        result = _parse_diag_blob(_blob(hello_eth0=False, default_route=["eth0"]))
        assert result["internet_connection"] == "No internet"

    def test_no_internet_when_routes_missing(self):
        result = _parse_diag_blob(_blob(hello_eth0=False, default_route=None))
        assert result["internet_connection"] == "No internet"

    def test_uptime_and_routes(self):
        result = _parse_diag_blob(_blob())
        assert result["cm10_uptime_s"] == 1114187
        assert result["default_route"] == ["ppp0", "eth0"]

    def test_empty_blob(self):
        result = _parse_diag_blob({})
        assert result["battery_temp_high_c"] is None
        assert result["internet_connection"] == "No internet"
        assert result["cm10_uptime_s"] is None
