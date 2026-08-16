# Feed Watch — CCTV Black-Feed Monitor

Monitors your Dahua channels for black/dead feeds, logs every status change
to SQLite, and shows it all on a custom dashboard. Supports two input modes:
**live RTSP polling** and **recorded file backtesting**.

Every piece of this has been tested against synthetic frames and a synthetic
video clip before being handed to you — the detection thresholds, the
incident open/close logic, and every API endpoint all behave as expected.
You're plugging in real camera URLs, not debugging the scaffolding.

---

## Running with Docker (recommended)

Skips the venv/pip setup entirely — one image, two containers (monitor +
dashboard), sharing the SQLite file through a named volume.

```bash
# 1. edit config.py with your real RTSP URLs first
docker compose up --build -d

# check it's working
docker compose logs -f monitor      # should show OK/BLACK lines per channel
docker compose logs -f dashboard
```

Then open **http://localhost:8501**.

- `config.py` is bind-mounted read-only into both containers, so editing
  channels/thresholds only needs `docker compose restart monitor dashboard`
  — no rebuild.
- The SQLite file lives in the `cctv-data` named volume, not inside the
  container, so `docker compose down` / rebuilds don't lose your history.
  Back it up with:
  ```bash
  docker run --rm -v cctv-monitor_cctv-data:/data -v $(pwd):/backup \
    alpine cp /data/cctv_monitor.db /backup/
  ```
- If the containers can't reach your NVR/cameras over the default bridge
  network (uncommon, but happens with some VLAN/multicast setups), switch
  `monitor` in `docker-compose.yml` to `network_mode: host` (Linux only).
- Stop everything: `docker compose down` (add `-v` to also delete the data volume).
- File-mode backtests still work in Docker:
  ```bash
  docker compose run --rm monitor python3 monitor.py --file /path/to/recording.mp4 \
      --channel-id CH02 --channel-name "D109 Home Care" --sample-every 5 \
      --clip-start "2026-08-16T08:45:00"
  ```
  (mount the recording's folder into the container first if it's not already under `.`)

## Running without Docker

### 1. Install

```bash
cd cctv-monitor
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your channels

Edit `config.py`:

```python
CHANNELS = [
    {
        "channel_id": "CH01",
        "channel_name": "D108 Front Desk",
        "source": "rtsp://admin:YOUR_PASSWORD@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1",
    },
    ...
]
```

- Get your NVR's IP, RTSP port (default 554), username/password from the
  Dahua NVR's network settings.
- `subtype=1` requests the sub-stream (lower resolution) — plenty for a
  brightness/texture check and much lighter on bandwidth than the main
  stream (`subtype=0`).
- `channel=N` matches the channel number shown in your NVR UI (CH01, CH02, ...).

Also tune, if needed:
- `BRIGHTNESS_THRESHOLD` / `STD_DEV_THRESHOLD` in `config.py` — the defaults
  (10.0 / 5.0) correctly separated pure-black from dim-but-textured IR night
  frames in testing, but every camera's noise floor differs slightly. If you
  get false positives at night, raise `STD_DEV_THRESHOLD` a little; if real
  blackouts aren't being caught, lower it.
- `POLL_INTERVAL_SEC` — how often each channel is checked (default 30s).

### 3. Initialize the database

```bash
python3 db.py
```

Creates `cctv_monitor.db` in the project folder — nothing to install, no
external DB server, no retention/expiry to worry about.

### 4. Run the monitor

**Live mode** — polls every RTSP channel in `config.py` forever:

```bash
python3 monitor.py
```

Run this as a background service (systemd, pm2, `screen` — whatever you're
comfortable with) so it survives reboots. A minimal systemd unit:

```ini
[Unit]
Description=CCTV Feed Monitor
After=network.target

[Service]
WorkingDirectory=/path/to/cctv-monitor
ExecStart=/path/to/cctv-monitor/venv/bin/python3 monitor.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**File / backtest mode** — classify an already-recorded clip instead of
polling live (e.g. to audit yesterday's export, or validate thresholds
against a clip you know contains a blackout):

```bash
python3 monitor.py --file /path/to/recording.mp4 \
    --channel-id CH02 --channel-name "D109 Home Care" \
    --sample-every 5 \
    --clip-start "2026-08-16T08:45:00"
```

- `--clip-start` should be the real wall-clock time the recording begins —
  read it off the NVR's on-screen timestamp or the export filename — so the
  incidents land at the correct time on the dashboard instead of at
  clip-relative offsets.
- `--sample-every` controls how many seconds between sampled frames (default
  5s) — no need to check every single frame of a 25fps recording.
- Both modes write into the **same** `cctv_monitor.db` and `channel_id` —
  so file-mode backtests of past footage and live polling going forward
  show up together on one timeline.

### 5. Run the dashboard

```bash
streamlit run app.py
```

Then open **http://localhost:8501** (or `http://<server-ip>:8501` from
another machine on your network). The dashboard reads directly from
`cctv_monitor.db` — no separate backend/API process needed, `app.py` is
the whole thing. It auto-refreshes every 15 seconds.

To run it as a background service alongside `monitor.py`, add a second
systemd unit (same pattern as above) with:
```ini
ExecStart=/path/to/cctv-monitor/venv/bin/streamlit run app.py --server.headless true --server.port 8501
```

## What you'll see

- **Live Status** — one tile per channel, styled like the camera's own OSD,
  green/red/amber for ok/black/no_signal, with "black for Xm" on anything down.
- **24H Timeline** — a per-channel strip across the day, 10-minute buckets,
  so a blackout jumps out visually and you can hover a segment for its exact time.
- **Uptime — Trailing 7 Days** — per-channel uptime %, incident count, total downtime.
- **Incident Log** — every blackout/no-signal event with start, end, duration,
  filterable by the date picker at the top.

All of it re-polls itself (live tiles every 15s, everything else every 1–2min),
so you can leave it open on a wall monitor.

## Files

| File | Purpose |
|---|---|
| `config.py` | Channel list, detection thresholds, poll interval |
| `detector.py` | Frame → ok/black classification (brightness + std-dev) |
| `capture.py` | RTSP single-frame grab / video-file frame iterator |
| `db.py` | SQLite schema + incident open/close logic |
| `monitor.py` | CLI entrypoint — live loop or file backtest |
| `queries.py` | Read-only SQLite query functions used by the dashboard |
| `app.py` | The Streamlit dashboard itself — `streamlit run app.py` |
| `Dockerfile` | Image used by both the monitor and dashboard containers |
| `docker-compose.yml` | Runs both services, sharing one SQLite volume |

## Troubleshooting

- **`no_signal` on every check** → RTSP URL/credentials wrong, or the NVR
  doesn't allow that many concurrent RTSP connections — test the URL
  directly first: `ffplay "rtsp://user:pass@ip:554/cam/realmonitor?channel=1&subtype=1"`.
- **False "black" during night/IR footage** → raise `STD_DEV_THRESHOLD` in
  `config.py`, since IR-lit frames are dim but still have sensor grain.
- **Dashboard shows no data for a channel** → its `channel_id` in `config.py`
  must exactly match what was used when writing to the DB (live or file mode).
- **Dashboard and monitor both need to run** → `monitor.py` is the writer
  (polls cameras, fills the DB), `app.py` is the reader (shows it). Run both;
  neither does the other's job.
- **Docker: monitor container can't reach the NVR** → see the `network_mode: host`
  note above; also confirm the RTSP URL works from the host first with `ffplay`
  before blaming the container.
