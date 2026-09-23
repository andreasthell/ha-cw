"""Constants for the CheckWatt integration."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from homeassistant.const import Platform

DOMAIN = "checkwatt"
PLATFORMS = [Platform.SENSOR, Platform.EVENT]

UPDATE_INTERVAL = timedelta(seconds=60)
REVENUE_UPDATE_INTERVAL = timedelta(minutes=15)
PRICE_UPDATE_INTERVAL = timedelta(minutes=60)
ENERGY_UPDATE_INTERVAL = timedelta(minutes=15)
LOGBOOK_UPDATE_INTERVAL = timedelta(minutes=30)
DIAG_UPDATE_INTERVAL = timedelta(minutes=5)
NEWS_UPDATE_INTERVAL = timedelta(hours=4)

# Slow updates run on their own intervals; their status is shown per name on
# the "Last API poll" sensor.
SLOW_UPDATES = ("revenue", "price", "energy", "logbook", "diagnostics", "news")

# A failed slow update is retried after this instead of its full interval.
SLOW_RETRY_INTERVAL = timedelta(minutes=5)

# CM10 diagnostics older than this are treated as unknown. The CM10 does not
# report every cycle — a healthy site's blob can be over an hour old.
DIAG_MAX_AGE = timedelta(hours=3)

# The API's dates (revenue days, spot price slots, yearly totals) are Swedish
# local time, regardless of where the HA host runs.
API_TZ = ZoneInfo("Europe/Stockholm")
