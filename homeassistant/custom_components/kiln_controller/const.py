"""Constants for the Kiln Controller integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "kiln_controller"

# Config / options keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 8081
DEFAULT_SCAN_INTERVAL = 10  # seconds

MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 300

# Keys returned by the kiln-controller /api/status payload
ATTR_STATE = "state"
ATTR_PROFILE = "profile"
ATTR_TEMP_SCALE = "temp_scale"
ATTR_START_TIME = "start_time"
ATTR_RUNTIME = "runtime"
ATTR_TOTALTIME = "totaltime"
ATTR_TIME_REMAINING = "time_remaining"
ATTR_PROFILE_DATA = "profile_data"
ATTR_TARGET = "target"

STATE_RUNNING = "RUNNING"

UPDATE_LISTENER_TIMEOUT = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
