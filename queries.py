"""
Read-only query functions against the monitor's SQLite DB, used directly by
the Streamlit dashboard (app.py). No API/HTTP layer needed -- Streamlit runs
in the same Python process, so it just calls these functions.

Kept separate from db.py (which owns writes + schema) so the dashboard code
only ever imports read paths.
"""

from datetime import datetime, timedelta
from typing import Optional

import db
from config import CHANNELS, TIMEZONE


def parse_date(date_str: Optional[str]):
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
    else:
        d = datetime.now(TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return d, d + timedelta(days=1)


def get_live_status():
    """Most recent check per channel + how long it's been in that state."""
    out = []
    with db.get_conn() as conn:
        for ch in CHANNELS:
            latest = conn.execute(
                "SELECT * FROM checks WHERE channel_id = ? ORDER BY ts DESC LIMIT 1",
                (ch["channel_id"],),
            ).fetchone()

            open_incident = conn.execute(
                "SELECT * FROM incidents WHERE channel_id = ? AND end_ts IS NULL "
                "ORDER BY start_ts DESC LIMIT 1",
                (ch["channel_id"],),
            ).fetchone()

            out.append({
                "channel_id": ch["channel_id"],
                "channel_name": ch["channel_name"],
                "status": latest["status"] if latest else "unknown",
                "last_checked": latest["ts"] if latest else None,
                "since": open_incident["start_ts"] if open_incident else None,
            })
    return out


def get_timeline(date_str: Optional[str], bucket_minutes: int = 10):
    """
    Per channel, a list of {start, status} buckets covering the requested
    day. A bucket is 'black'/'no_signal' if ANY check in that window was
    bad, 'ok' if it has data and none were bad, else 'no_data'.
    """
    day_start, day_end = parse_date(date_str)
    bucket = timedelta(minutes=bucket_minutes)

    result = {}
    with db.get_conn() as conn:
        for ch in CHANNELS:
            rows = list(conn.execute(
                "SELECT ts, status FROM checks WHERE channel_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
                (ch["channel_id"], day_start.isoformat(), day_end.isoformat()),
            ).fetchall())

            buckets = []
            cursor = day_start
            row_idx = 0
            while cursor < day_end:
                bucket_end = cursor + bucket
                statuses_in_bucket = []
                while row_idx < len(rows) and datetime.fromisoformat(rows[row_idx]["ts"]) < bucket_end:
                    statuses_in_bucket.append(rows[row_idx]["status"])
                    row_idx += 1

                if not statuses_in_bucket:
                    bstatus = "no_data"
                elif any(s == "black" for s in statuses_in_bucket):
                    bstatus = "black"
                elif any(s == "no_signal" for s in statuses_in_bucket):
                    bstatus = "no_signal"
                else:
                    bstatus = "ok"

                buckets.append({"start": cursor, "end": bucket_end, "status": bstatus})
                cursor = bucket_end

            result[ch["channel_id"]] = {"channel_name": ch["channel_name"], "buckets": buckets}
    return result


def get_incidents(date_str: Optional[str] = None, days: int = 1, channel_id: Optional[str] = None):
    day_start, _ = parse_date(date_str)
    window_end = day_start + timedelta(days=days)

    query = "SELECT * FROM incidents WHERE start_ts >= ? AND start_ts < ?"
    params = [day_start.isoformat(), window_end.isoformat()]
    if channel_id:
        query += " AND channel_id = ?"
        params.append(channel_id)
    query += " ORDER BY start_ts DESC"

    with db.get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_stats(days: int = 7):
    """Per-channel uptime % and incident count over the trailing `days` days."""
    window_start = (datetime.now(TIMEZONE) - timedelta(days=days)).isoformat()
    out = []
    with db.get_conn() as conn:
        for ch in CHANNELS:
            total = conn.execute(
                "SELECT COUNT(*) c FROM checks WHERE channel_id = ? AND ts >= ?",
                (ch["channel_id"], window_start),
            ).fetchone()["c"]

            ok_count = conn.execute(
                "SELECT COUNT(*) c FROM checks WHERE channel_id = ? AND ts >= ? AND status = 'ok'",
                (ch["channel_id"], window_start),
            ).fetchone()["c"]

            incident_count = conn.execute(
                "SELECT COUNT(*) c FROM incidents WHERE channel_id = ? AND start_ts >= ?",
                (ch["channel_id"], window_start),
            ).fetchone()["c"]

            total_bad_sec = conn.execute(
                "SELECT COALESCE(SUM(duration_sec),0) s FROM incidents "
                "WHERE channel_id = ? AND start_ts >= ? AND duration_sec IS NOT NULL",
                (ch["channel_id"], window_start),
            ).fetchone()["s"]

            uptime_pct = round(100 * ok_count / total, 2) if total > 0 else None

            out.append({
                "channel_id": ch["channel_id"],
                "channel_name": ch["channel_name"],
                "uptime_pct": uptime_pct,
                "total_checks": total,
                "incident_count": incident_count,
                "total_downtime_sec": total_bad_sec,
            })

    out.sort(key=lambda x: (x["uptime_pct"] is None, x["uptime_pct"]))
    return out
