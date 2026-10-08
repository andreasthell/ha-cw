"""Tests for the mFRR activation binary sensor."""

from datetime import UTC, datetime
from types import SimpleNamespace

from custom_components.checkwatt.binary_sensor import CheckwattMfrrActivationSensor


def _sensor(**data) -> CheckwattMfrrActivationSensor:
    coordinator = SimpleNamespace(
        data={"rpi_serial": "aabbccddeeff", **data}, last_update_success=True
    )
    return CheckwattMfrrActivationSensor(coordinator)


class TestMfrrActivationSensor:
    def test_unavailable_until_first_fetch(self):
        sensor = _sensor(mfrr_activation_active=None, mfrr_activation=None)
        assert sensor.available is False
        assert sensor.extra_state_attributes is None

    def test_off_shows_latest_activation(self):
        activation = {
            "direction": "up",
            "start": datetime(2026, 10, 7, 4, 34, tzinfo=UTC),
            "end": datetime(2026, 10, 7, 5, 5, tzinfo=UTC),
            "power_w": 5614.48,
            "ramp_up_s": 600,
            "ramp_down_s": 600,
        }
        sensor = _sensor(mfrr_activation_active=False, mfrr_activation=activation)
        assert sensor.available is True
        assert sensor.is_on is False
        assert sensor.extra_state_attributes["direction"] == "up"
        assert sensor.extra_state_attributes["power_w"] == 5614
