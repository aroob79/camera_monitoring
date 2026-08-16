"""
Entry point. Two modes:

  Live mode (default) -- polls every channel in config.CHANNELS on a loop,
  forever, writing status to SQLite. This is what you run as a background
  service against your NVR/cameras.

      python3 monitor.py
      python3 monitor.py --once          # single pass over all channels, then exit

  File mode -- backtests a single recorded video against the same detector,
  useful for (a) validating thresholds against footage you already know is
  good/bad, or (b) auditing exported recordings you didn't monitor live.

      python3 monitor.py --file /path/to/recording.mp4 --channel-id CH02 \\
          --channel-name "D109 Home Care" --sample-every 5 \\
          --clip-start "2026-08-16T08:45:00"

  `--clip-start` is the real-world timestamp the recording begins at (e.g.
  from the NVR's on-screen clock or filename) so incidents land on the
  correct wall-clock time in the dashboard instead of clip-relative seconds.
"""

import argparse
import time
from datetime import datetime, timedelta, timezone

import db
from capture import grab_single_frame, iter_file_frames, is_rtsp
from detector import classify_frame
from config import CHANNELS, POLL_INTERVAL_SEC, TIMEZONE


def poll_channel_once(channel):
    frame, err = grab_single_frame(channel["source"])
    ts = db.now_iso()

    if err is not None:
        result = {"status": "no_signal", "mean_brightness": None, "std_dev": None}
    else:
        result = classify_frame(frame)

    db.insert_check(
        channel["channel_id"], channel["channel_name"],
        result["status"], result["mean_brightness"], result["std_dev"], ts=ts,
    )
    db.handle_status_transition(channel["channel_id"], channel["channel_name"], result["status"], ts=ts)

    return result["status"]


def run_live(loop_forever=True):
    db.init_db()
    print(f"Monitoring {len(CHANNELS)} channel(s), polling every {POLL_INTERVAL_SEC}s. Ctrl+C to stop.")
    while True:
        for ch in CHANNELS:
            if not is_rtsp(ch["source"]):
                print(f"[skip] {ch['channel_id']}: source is not an rtsp:// URL, skipping in live mode")
                continue
            status = poll_channel_once(ch)
            marker = "OK" if status == "ok" else f"** {status.upper()} **"
            print(f"{datetime.now(TIMEZONE).isoformat(timespec='seconds')}  {ch['channel_id']:6s} {ch['channel_name']:20s} {marker}")
        if not loop_forever:
            break
        time.sleep(POLL_INTERVAL_SEC)


def run_file(path, channel_id, channel_name, sample_every_sec, clip_start_iso):
    db.init_db()
    clip_start = datetime.fromisoformat(clip_start_iso) if clip_start_iso else datetime.now(TIMEZONE)
    if clip_start.tzinfo is None:
        clip_start = clip_start.replace(tzinfo=TIMEZONE)

    print(f"Backtesting {path} as {channel_id} ({channel_name}), sampling every {sample_every_sec}s")
    count = 0
    for offset_sec, frame in iter_file_frames(path, sample_every_sec=sample_every_sec):
        ts = (clip_start + timedelta(seconds=offset_sec)).isoformat()
        result = classify_frame(frame)
        db.insert_check(channel_id, channel_name, result["status"], result["mean_brightness"], result["std_dev"], ts=ts)
        db.handle_status_transition(channel_id, channel_name, result["status"], ts=ts)
        count += 1
        if result["status"] != "ok":
            print(f"  {ts}  {result['status'].upper()}  (mean={result['mean_brightness']}, std={result['std_dev']})")
    print(f"Done. {count} samples processed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCTV black-feed monitor")
    parser.add_argument("--once", action="store_true", help="single pass over all live channels, then exit")
    parser.add_argument("--file", type=str, help="path to a recorded video file to backtest instead of live polling")
    parser.add_argument("--channel-id", type=str, default="CH01", help="channel id to tag file-mode results with")
    parser.add_argument("--channel-name", type=str, default="Unnamed", help="channel name to tag file-mode results with")
    parser.add_argument("--sample-every", type=float, default=5.0, help="seconds between sampled frames in file mode")
    parser.add_argument("--clip-start", type=str, default=None, help="ISO8601 wall-clock time the recording starts at")
    args = parser.parse_args()

    if args.file:
        run_file(args.file, args.channel_id, args.channel_name, args.sample_every, args.clip_start)
    else:
        run_live(loop_forever=not args.once)
