"""Runtime configuration, read from environment variables."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(os.environ.get("BEST_DEAL_DB", Path.cwd() / "data" / "best_deal.db"))
TIMEZONE = ZoneInfo(os.environ.get("BEST_DEAL_TZ", "Asia/Singapore"))
CURRENCY = os.environ.get("BEST_DEAL_CURRENCY", "SGD")
# "none" (built-in places + "lat,lng" only) or "nominatim" (OpenStreetMap lookup).
GEOCODER = os.environ.get("BEST_DEAL_GEOCODER", "none").lower()
# Minimum observed prices per product before estimates are calibrated to them.
CALIBRATION_MIN_SAMPLES = int(os.environ.get("BEST_DEAL_CALIBRATION_MIN", "3"))
# When set, every request except /healthz needs HTTP Basic auth with this password.
PASSWORD = os.environ.get("BEST_DEAL_PASSWORD") or None
