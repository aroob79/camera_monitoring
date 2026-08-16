"""
Feed Watch — CCTV Uptime Monitor (Streamlit dashboard)

Run with:
    streamlit run app.py

Reads directly from the SQLite DB that monitor.py writes to (via queries.py).
No separate backend process needed -- this is the whole dashboard.
"""

from datetime import datetime
import config

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import queries

# ---------------------------------------------------------------- page setup
st.set_page_config(
    page_title="Feed Watch — CCTV Uptime Monitor",
    page_icon="🎥",
    layout="wide",
)

COLORS = {
    "ok": "#33c46a",
    "black": "#e5484d",
    "no_signal": "#f0a93a",
    "no_data": "#2a323b",
    "unknown": "#2a323b",
}
DIM = {
    "ok": "#1c3d29",
    "black": "#3d1f21",
    "no_signal": "#3d321a",
}

st.markdown(f"""
<style>
    .stApp {{ background-color: #0a0d10; }}
    .block-container {{ padding-top: 1.5rem; max-width: 1300px; }}
    h1, h2, h3 {{ color: #e7ebee !important; }}
    [data-testid="stMetricValue"] {{ font-family: 'JetBrains Mono', monospace; }}
    .fw-tile {{
        background:#12161b; border:1px solid #232a32; border-radius:8px;
        overflow:hidden; margin-bottom:10px;
    }}
    .fw-feed {{
        height:70px; background:#000; position:relative;
        display:flex; align-items:flex-end; justify-content:flex-end;
    }}
    .fw-osd-time {{ font-family:'JetBrains Mono',monospace; font-size:10.5px; color:rgba(255,255,255,0.55); padding:5px 7px; }}
    .fw-osd-name {{ position:absolute; left:8px; bottom:6px; font-family:'JetBrains Mono',monospace; font-size:10.5px; color:rgba(255,255,255,0.5); }}
    .fw-dot {{ position:absolute; top:7px; left:8px; width:7px; height:7px; border-radius:50%; }}
    .fw-info {{ padding:9px 12px 11px; }}
    .fw-chid {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:#4d5761; }}
    .fw-chname {{ font-size:13.5px; font-weight:600; color:#e7ebee; margin-top:1px; }}
    .fw-status-row {{ display:flex; align-items:center; justify-content:space-between; margin-top:8px; }}
    .fw-pill {{ font-family:'JetBrains Mono',monospace; font-size:10.5px; padding:3px 7px; border-radius:4px; text-transform:uppercase; font-weight:600; }}
    .fw-since {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:#4d5761; }}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------- auto-refresh
st_autorefresh(interval=15_000, key="live_refresh")

# ------------------------------------------------------------------ header
h_left, h_right = st.columns([3, 1])
with h_left:
    st.markdown("## 🎥 Feed Watch <span style='color:#7c8794; font-size:16px;'>· CCTV Uptime Monitor</span>", unsafe_allow_html=True)
with h_right:
    selected_date = st.date_input("Date", value=datetime.now(config.TIMEZONE).date())

date_str = selected_date.strftime("%Y-%m-%d")

# ------------------------------------------------------------ live status
st.markdown("#### Live Status")
live = queries.get_live_status()

cols = st.columns(4)
for i, ch in enumerate(live):
    status = ch["status"] if ch["status"] in COLORS else "no_signal"
    color = COLORS[status]
    dim = DIM.get(status, "#2a323b")

    if ch["last_checked"]:
        osd_time = datetime.fromisoformat(ch["last_checked"]).strftime("%Y-%m-%d %H:%M:%S")
    else:
        osd_time = "—"

    if status != "ok" and ch["since"]:
        since_dt = datetime.fromisoformat(ch["since"])
        elapsed = int((datetime.now(config.TIMEZONE) - since_dt).total_seconds())
        since_txt = f"for {elapsed//60}m {elapsed%60}s" if elapsed < 3600 else f"for {elapsed//3600}h {(elapsed%3600)//60}m"
    else:
        since_txt = ""

    with cols[i % 4]:
        st.markdown(f"""
        <div class="fw-tile" style="border-color:{color if status!='ok' else '#232a32'};">
            <div class="fw-feed" style="background-color:{'#0d1a12' if status=='ok' else ('#1a140a' if status=='no_signal' else '#000')};">
                <div class="fw-dot" style="background:{color}; box-shadow:0 0 6px {color};"></div>
                <div class="fw-osd-name">{ch['channel_id']}</div>
                <div class="fw-osd-time">{osd_time}</div>
            </div>
            <div class="fw-info">
                <div class="fw-chid">{ch['channel_id']}</div>
                <div class="fw-chname">{ch['channel_name']}</div>
                <div class="fw-status-row">
                    <span class="fw-pill" style="color:{color}; background:{dim};">{status.replace('_',' ')}</span>
                    <span class="fw-since">{since_txt}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.caption(f"updated {datetime.now(config.TIMEZONE).strftime('%H:%M:%S')} · refreshes every 15s")

# --------------------------------------------------------------- timeline
st.markdown("#### 24H Timeline")
timeline = queries.get_timeline(date_str, bucket_minutes=10)

fig = go.Figure()
channel_ids = list(timeline.keys())
for ch_id in channel_ids:
    info = timeline[ch_id]
    for b in info["buckets"]:
        fig.add_trace(go.Scatter(
            x=[b["start"], b["end"]],
            y=[ch_id, ch_id],
            mode="lines",
            line=dict(color=COLORS.get(b["status"], "#2a323b"), width=18),
            hoverinfo="text",
            text=f"{ch_id} · {b['start'].strftime('%H:%M')} · {b['status']}",
            showlegend=False,
        ))

fig.update_layout(
    height=90 + 45 * len(channel_ids),
    plot_bgcolor="#12161b",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e7ebee", family="JetBrains Mono"),
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(showgrid=False, tickformat="%H:%M", color="#7c8794"),
    yaxis=dict(showgrid=False, autorange="reversed", color="#e7ebee"),
)
st.plotly_chart(fig, width='stretch')

legend_cols = st.columns(4)
for i, (label, color) in enumerate([("OK", COLORS["ok"]), ("Black", COLORS["black"]),
                                      ("No signal", COLORS["no_signal"]), ("No data", COLORS["no_data"])]):
    legend_cols[i].markdown(f"<span style='color:{color};'>●</span> {label}", unsafe_allow_html=True)

# ------------------------------------------------------------------ stats
st.markdown("#### Uptime — Trailing 7 Days")
stats = queries.get_stats(days=7)

stat_cols = st.columns(len(stats)) if stats else []
for i, s in enumerate(stats):
    with stat_cols[i]:
        pct = s["uptime_pct"] if s["uptime_pct"] is not None else 0
        st.metric(f"{s['channel_id']} · {s['channel_name']}", f"{pct}%" if s["uptime_pct"] is not None else "n/a")
        st.progress(min(int(pct), 100))
        downtime = s["total_downtime_sec"]
        downtime_txt = f"{downtime//60}m {downtime%60}s" if downtime < 3600 else f"{downtime//3600}h {(downtime%3600)//60}m"
        st.caption(f"{s['incident_count']} incidents · {downtime_txt} downtime")

# --------------------------------------------------------------- incidents
st.markdown("#### Incident Log")

channel_options = ["All channels"] + [c["channel_id"] for c in queries.CHANNELS]
filter_col1, filter_col2 = st.columns([1, 3])
with filter_col1:
    selected_channel = st.selectbox("Channel", channel_options)

channel_filter = None if selected_channel == "All channels" else selected_channel
incidents = queries.get_incidents(date_str, days=1, channel_id=channel_filter)

if not incidents:
    st.info(f"No incidents recorded for {date_str}" + (f" on {channel_filter}" if channel_filter else ""))
else:
    df = pd.DataFrame(incidents)
    df["Channel"] = df["channel_id"] + " — " + df["channel_name"]
    df["Type"] = df.apply(lambda r: r["status"].replace("_", " ") if r["end_ts"] else "ongoing", axis=1)
    df["Start"] = (
    pd.to_datetime(df["start_ts"], errors="coerce")
    .dt.strftime("%b %d, %H:%M:%S")
    .fillna("—")
)
    df["End"] = (
    pd.to_datetime(df["end_ts"], errors="coerce")
    .dt.strftime("%b %d, %H:%M:%S")
    .fillna("—")
)

    def fmt_dur(sec):
        if pd.isna(sec):
            return "—"

        sec = int(sec)

        if sec < 60:
            return f"{sec}s"
        elif sec < 3600:
            return f"{sec//60}m {sec%60}s"
        else:
            return f"{sec//3600}h {(sec%3600)//60}m"
        
    df["Duration"] = df["duration_sec"].apply(fmt_dur)

    st.dataframe(
        df[["Channel", "Type", "Start", "End", "Duration"]],
        width="stretch",
        hide_index=True,
    )
    st.caption(f"{len(incidents)} incident(s)")
