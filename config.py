"""
Central configuration for the CCTV black-feed monitor.
Edit CHANNELS to match your Dahua NVR channel list.
"""

import ast
import os

from pathlib import Path

from dotenv import load_dotenv
from datetime import timezone, timedelta

# --- Channel list -----------------------------------------------------------
# `source` can be:
#   - an RTSP URL (live monitoring)              -> "rtsp://user:pass@192.168.1.108:554/cam/realmonitor?channel=2&subtype=1"
#   - a path to a recorded video file (backtest)  -> "/home/claude/samples/ch02_sample.mp4"
#   - a path to a folder of recorded files        -> handled by monitor.py --file mode, one file at a time



# Load .env file — looks for it next to this file (backend/.env)
load_dotenv(Path(__file__).parent / ".env")
RTSP_SOURCES: dict = ast.literal_eval(os.getenv("rtsp"))


CHANNELS = []
for channel_id, source in RTSP_SOURCES.items():

    CHANNELS.append({
        "channel_id": "_".join(channel_id.split("_")[-3:]),  # e.g. "ch01" -> "01"
        "channel_name": channel_id,
        "source": source,
    })


# --- Detection thresholds ----------------------------------------------------
# A frame is classified "black" when BOTH conditions hold:
#   mean brightness (0-255 grayscale) is below BRIGHTNESS_THRESHOLD
#   AND standard deviation (texture/detail) is below STD_DEV_THRESHOLD
# Tune these by running tools/calibrate.py against a few known-good and
# known-black frames from your own cameras -- IR night frames are dim but
# still have grain/texture, so std-dev is what actually separates
# "black feed" from "dark but working" nighttime footage.
BRIGHTNESS_THRESHOLD = 20.0
STD_DEV_THRESHOLD = 20

# --- Polling ------------------------------------------------------------------
POLL_INTERVAL_SEC = int(60 * 5)         # how often to sample each RTSP channel
RTSP_OPEN_TIMEOUT_MS = 5000     # give up connecting after this long -> no_signal
RTSP_READ_RETRIES = 2           # retries before declaring no_signal

# --- Storage -------------------------------------------------------------------
# Overridable via env var so the monitor and dashboard containers can be
# pointed at the same file living on a shared Docker volume.
DB_PATH = os.environ.get("DB_PATH", "cctv_monitor.db")

# Default local timezone: Bangladesh Time (UTC+6)
TIMEZONE = timezone(timedelta(hours=6))
