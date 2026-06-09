"""Constants for the CheckWatt integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "checkwatt"
PLATFORMS = [Platform.SENSOR, Platform.EVENT]

UPDATE_INTERVAL = timedelta(seconds=60)
REVENUE_UPDATE_INTERVAL = timedelta(minutes=15)
PRICE_UPDATE_INTERVAL = timedelta(minutes=60)
ENERGY_UPDATE_INTERVAL = timedelta(minutes=15)
LOGBOOK_UPDATE_INTERVAL = timedelta(minutes=30)
