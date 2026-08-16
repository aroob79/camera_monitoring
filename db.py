"""
SQLite storage layer.

Two tables:
  checks     -- one row per poll, raw log (never modified after insert)
  incidents  -- one row per continuous black/no_signal episode
               (opened when status flips away from 'ok', closed when it flips back)

Keeping `incidents` as its own table means the dashboard never has to
scan/aggregate the raw `checks` table to answer "how long was CH02 down
today" -- that's a single indexed query.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_PATH, TIMEZONE

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT NOT NULL,          -- ISO8601 UTC
    channel_id        TEXT NOT NULL,
    channel_name      TEXT,
    status            TEXT NOT NULL,          -- 'ok' | 'black' | 'no_signal'
    mean_brightness   REAL,
    std_dev           REAL
);
CREATE INDEX IF NOT EXISTS idx_checks_channel_ts ON checks (channel_id, ts);

CREATE TABLE IF NOT EXISTS incidents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id        TEXT NOT NULL,
    channel_name      TEXT,
    status            TEXT NOT NULL,          -- 'black' | 'no_signal'
    start_ts          TEXT NOT NULL,
    end_ts            TEXT,                   -- NULL while ongoing
    duration_sec      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_incidents_channel ON incidents (channel_id, start_ts);

-- tracks the last known status per channel so the monitor loop can detect
-- ok->bad and bad->ok transitions without re-reading the whole checks table
CREATE TABLE IF NOT EXISTS channel_state (
    channel_id        TEXT PRIMARY KEY,
    last_status       TEXT NOT NULL,
    open_incident_id  INTEGER
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # allow concurrent read (dashboard) + write (monitor)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def now_iso():
    return datetime.now(TIMEZONE).isoformat()


def insert_check(channel_id, channel_name, status, mean_brightness, std_dev, ts=None):
    ts = ts or now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO checks (ts, channel_id, channel_name, status, mean_brightness, std_dev) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, channel_id, channel_name, status, mean_brightness, std_dev),
        )
    return ts


def get_channel_state(conn, channel_id):
    row = conn.execute(
        "SELECT * FROM channel_state WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row


def handle_status_transition(channel_id, channel_name, status, ts=None):
    """
    Call this once per poll, after insert_check. Opens/closes rows in
    `incidents` whenever a channel flips between 'ok' and a bad status.
    Bad statuses ('black', 'no_signal') are treated as one incident type
    for open/close purposes but the status value itself is preserved.
    """
    ts = ts or now_iso()
    is_bad = status in ("black", "no_signal")

    with get_conn() as conn:
        state = get_channel_state(conn, channel_id)

        if state is None:
            # first time we've seen this channel
            open_incident_id = None
            if is_bad:
                cur = conn.execute(
                    "INSERT INTO incidents (channel_id, channel_name, status, start_ts) "
                    "VALUES (?, ?, ?, ?)",
                    (channel_id, channel_name, status, ts),
                )
                open_incident_id = cur.lastrowid
            conn.execute(
                "INSERT INTO channel_state (channel_id, last_status, open_incident_id) "
                "VALUES (?, ?, ?)",
                (channel_id, status, open_incident_id),
            )
            return

        was_bad = state["last_status"] in ("black", "no_signal")

        if is_bad and not was_bad:
            # ok -> bad: open a new incident
            cur = conn.execute(
                "INSERT INTO incidents (channel_id, channel_name, status, start_ts) "
                "VALUES (?, ?, ?, ?)",
                (channel_id, channel_name, status, ts),
            )
            conn.execute(
                "UPDATE channel_state SET last_status = ?, open_incident_id = ? WHERE channel_id = ?",
                (status, cur.lastrowid, channel_id),
            )

        elif is_bad and was_bad:
            # still bad, nothing to open/close -- just refresh last_status
            # (status could have flipped between 'black' and 'no_signal', that's fine,
            # we keep the incident's original `status` value as first-observed)
            conn.execute(
                "UPDATE channel_state SET last_status = ? WHERE channel_id = ?",
                (status, channel_id),
            )

        elif not is_bad and was_bad:
            # bad -> ok: close the open incident
            incident_id = state["open_incident_id"]
            if incident_id is not None:
                inc = conn.execute(
                    "SELECT start_ts FROM incidents WHERE id = ?", (incident_id,)
                ).fetchone()
                if inc:
                    start_dt = datetime.fromisoformat(inc["start_ts"])
                    end_dt = datetime.fromisoformat(ts)
                    duration = int((end_dt - start_dt).total_seconds())
                    conn.execute(
                        "UPDATE incidents SET end_ts = ?, duration_sec = ? WHERE id = ?",
                        (ts, duration, incident_id),
                    )
            conn.execute(
                "UPDATE channel_state SET last_status = ?, open_incident_id = NULL WHERE channel_id = ?",
                (status, channel_id),
            )

        else:
            # ok -> ok, nothing to do
            pass


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
