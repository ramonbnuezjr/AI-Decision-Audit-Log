"""Streamlit governance dashboard for the AI Decision Audit Log.

Run with:
    streamlit run dashboard/app.py

Reads data/audit.db via the existing src/db/query layer — no new queries required.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Make src importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import get_connection  # noqa: E402
from src.db.query import (  # noqa: E402
    get_all_calls,
    get_errors,
    get_latency_stats,
    get_model_usage_summary,
    get_provider_health,
    get_session_activity,
)
from src.db.schema import ensure_schema  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Governance Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

DB_DEFAULT = str(Path(__file__).resolve().parent.parent / "data" / "audit.db")

with st.sidebar:
    st.title("AI Governance")
    st.caption("AI Decision Audit Log")

    db_path = st.text_input("Database path", value=DB_DEFAULT)
    refresh = st.button("Refresh data", use_container_width=True)

    st.divider()
    st.caption(f"DB: `{os.path.basename(db_path)}`")
    if Path(db_path).exists():
        size_kb = Path(db_path).stat().st_size / 1024
        st.caption(f"Size: {size_kb:,.1f} KB")
    else:
        st.warning("Database not found at the specified path.")

    st.divider()
    st.markdown(
        "**Commands**\n"
        "```bash\n"
        "# Run a batch of incidents\n"
        "python scripts/run_incidents.py \\\n"
        "  --input data/export.json \\\n"
        "  --limit 50 --max-tokens 300\n"
        "```"
    )

# ---------------------------------------------------------------------------
# Load data (cached per path, busted on refresh click)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading audit data…")
def load_data(path: str, _bust: int) -> dict:  # noqa: ANN001
    """Load all query results from the SQLite database.

    Args:
        path: Filesystem path to audit.db.
        _bust: Cache-bust counter (ignored in logic, changes cache key on refresh).

    Returns:
        Dict containing all query results needed by the dashboard.
    """
    with get_connection(path) as conn:
        ensure_schema(conn)
        all_entries = get_all_calls(conn)
        errors = get_errors(conn)
        health = get_provider_health(conn)
        latency = get_latency_stats(conn)
        usage = get_model_usage_summary(conn)
        sessions = get_session_activity(conn)
    return {
        "all": all_entries,
        "errors": errors,
        "health": health,
        "latency": latency,
        "usage": usage,
        "sessions": sessions,
    }


if "bust" not in st.session_state:
    st.session_state["bust"] = 0
if refresh:
    st.session_state["bust"] += 1
    st.cache_data.clear()

if not Path(db_path).exists():
    st.error(f"No database found at `{db_path}`. Run a capture first.")
    st.stop()

data = load_data(db_path, st.session_state["bust"])
all_entries = data["all"]
errors = data["errors"]
health_rows = data["health"]
latency = data["latency"]
usage_rows = data["usage"]
session_rows = data["sessions"]

if not all_entries:
    st.info("No entries in the audit log yet. Run a capture to get started.")
    st.stop()

# ---------------------------------------------------------------------------
# Derived aggregates
# ---------------------------------------------------------------------------

total_calls = len(all_entries)
success_calls = sum(1 for e in all_entries if e.status.value == "success")
success_rate = round(success_calls / total_calls * 100, 1) if total_calls else 0.0
total_in = sum(r["total_input_tokens"] for r in usage_rows)
total_out = sum(r["total_output_tokens"] for r in usage_rows)
total_tokens = total_in + total_out

cloud_in = sum(r["total_input_tokens"] for r in usage_rows if r["provider"] in ("anthropic", "openai"))
cloud_out = sum(r["total_output_tokens"] for r in usage_rows if r["provider"] in ("anthropic", "openai"))
est_cost = (cloud_in / 1_000_000 * 2.50) + (cloud_out / 1_000_000 * 10.00)

timestamps = sorted(e.timestamp for e in all_entries)
period_start = timestamps[0][:10]
period_end = timestamps[-1][:10]

# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

st.title("AI Governance Dashboard")
st.caption(f"Audit period: {period_start} → {period_end}  ·  {total_calls:,} total calls")
st.divider()

# ---------------------------------------------------------------------------
# Row 1 — KPI cards
# ---------------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)

k1.metric(
    label="Total Calls",
    value=f"{total_calls:,}",
    delta=f"{len(errors)} errors" if errors else "0 errors",
    delta_color="inverse",
)
k2.metric(
    label="Success Rate",
    value=f"{success_rate}%",
    delta=f"{success_calls:,} succeeded",
    delta_color="normal",
)
k3.metric(
    label="Total Tokens",
    value=f"{total_tokens:,}",
    delta=f"{total_in:,} in  /  {total_out:,} out",
    delta_color="off",
)
k4.metric(
    label="Est. Cloud Cost",
    value=f"${est_cost:.4f}",
    delta="GPT-4o pricing",
    delta_color="off",
)

st.divider()

# ---------------------------------------------------------------------------
# Row 2 — Provider Health
# ---------------------------------------------------------------------------

st.subheader("Provider Health")

ph_df = pd.DataFrame(health_rows)

fig_ph = go.Figure()
fig_ph.add_bar(
    name="Success",
    x=ph_df["provider"],
    y=ph_df["success_calls"],
    marker_color="#22c55e",
    text=ph_df["success_calls"],
    textposition="auto",
)
fig_ph.add_bar(
    name="Error",
    x=ph_df["provider"],
    y=ph_df["error_calls"],
    marker_color="#ef4444",
    text=ph_df["error_calls"],
    textposition="auto",
)
fig_ph.update_layout(
    barmode="group",
    xaxis_title="Provider",
    yaxis_title="Calls",
    legend_title="Status",
    height=300,
    margin=dict(t=10, b=10),
)
st.plotly_chart(fig_ph, use_container_width=True)

ph_cols = st.columns(len(health_rows))
for col, row in zip(ph_cols, health_rows):
    rate = row["success_rate"]
    icon = "✅" if rate == 100.0 else ("⚠️" if rate > 0 else "🔴")
    col.metric(
        label=f"{icon} {row['provider']}",
        value=f"{rate:.1f}%",
        delta=f"{row['success_calls']}/{row['total_calls']} succeeded",
        delta_color="normal" if rate > 50 else "inverse",
    )

st.divider()

# ---------------------------------------------------------------------------
# Row 3 — Latency profile  +  Token burn
# ---------------------------------------------------------------------------

col_lat, col_tok = st.columns(2)

with col_lat:
    st.subheader("Latency Profile")
    if latency["count"]:
        lat_df = pd.DataFrame(
            {
                "Percentile": ["p50 (median)", "p95", "max"],
                "Latency (ms)": [latency["p50"], latency["p95"], latency["max"]],
            }
        )
        fig_lat = px.bar(
            lat_df,
            x="Latency (ms)",
            y="Percentile",
            orientation="h",
            color="Percentile",
            color_discrete_sequence=["#3b82f6", "#f59e0b", "#ef4444"],
            text="Latency (ms)",
        )
        fig_lat.update_traces(texttemplate="%{text:,}ms", textposition="outside")
        fig_lat.update_layout(
            showlegend=False,
            height=250,
            margin=dict(t=10, b=10),
            xaxis_title="Milliseconds",
            yaxis_title="",
        )
        st.plotly_chart(fig_lat, use_container_width=True)
        st.caption(f"Based on {latency['count']:,} successful calls. Min: {latency['min']:,}ms")
    else:
        st.info("No successful calls recorded yet.")

with col_tok:
    st.subheader("Token Burn by Provider")
    tok_df = pd.DataFrame(
        [
            {
                "provider": r["provider"],
                "tokens": r["total_input_tokens"] + r["total_output_tokens"],
                "input": r["total_input_tokens"],
                "output": r["total_output_tokens"],
            }
            for r in usage_rows
            if (r["total_input_tokens"] + r["total_output_tokens"]) > 0
        ]
    )
    if not tok_df.empty:
        fig_tok = px.pie(
            tok_df,
            names="provider",
            values="tokens",
            hole=0.5,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_tok.update_traces(textinfo="label+percent")
        fig_tok.update_layout(height=250, margin=dict(t=10, b=10), showlegend=True)
        st.plotly_chart(fig_tok, use_container_width=True)
        st.caption(f"Total: {total_tokens:,} tokens  ({total_in:,} input / {total_out:,} output)")
    else:
        st.info("No token data recorded yet.")

st.divider()

# ---------------------------------------------------------------------------
# Row 4 — Calls over time
# ---------------------------------------------------------------------------

st.subheader("Calls Over Time")

ts_series = pd.to_datetime([e.timestamp for e in all_entries])
ts_df = pd.DataFrame({"timestamp": ts_series})
ts_df["hour"] = ts_df["timestamp"].dt.floor("h")
hourly = ts_df.groupby("hour").size().reset_index(name="calls")

if len(hourly) > 1:
    fig_ts = px.line(
        hourly,
        x="hour",
        y="calls",
        markers=True,
        labels={"hour": "Time", "calls": "Calls"},
        color_discrete_sequence=["#6366f1"],
    )
    fig_ts.update_layout(height=250, margin=dict(t=10, b=10))
    st.plotly_chart(fig_ts, use_container_width=True)
else:
    # Single hour — use a bar instead
    fig_ts = px.bar(
        hourly,
        x="hour",
        y="calls",
        labels={"hour": "Time", "calls": "Calls"},
        color_discrete_sequence=["#6366f1"],
    )
    fig_ts.update_layout(height=200, margin=dict(t=10, b=10))
    st.plotly_chart(fig_ts, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Row 5 — Session Activity
# ---------------------------------------------------------------------------

st.subheader("Session Activity")

ses_df = pd.DataFrame(session_rows)
ses_df = ses_df.rename(
    columns={
        "session_id": "Session",
        "total_calls": "Calls",
        "user_id": "User",
        "first_call": "First Call",
        "last_call": "Last Call",
        "error_calls": "Errors",
    }
)
ses_df["First Call"] = ses_df["First Call"].str[:16].str.replace("T", " ")
ses_df["Last Call"] = ses_df["Last Call"].str[:16].str.replace("T", " ")

st.dataframe(
    ses_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Calls": st.column_config.NumberColumn(format="%d"),
        "Errors": st.column_config.NumberColumn(format="%d"),
    },
    height=300,
)

st.divider()

# ---------------------------------------------------------------------------
# Row 6 — Error / Incident Log
# ---------------------------------------------------------------------------

st.subheader(f"Incident Log  ({len(errors)} errors)")

if errors:
    err_df = pd.DataFrame(
        [
            {
                "Timestamp": e.timestamp[:16].replace("T", " "),
                "Provider": e.provider,
                "Session": e.session_id,
                "Error": (e.error_message or "")[:120],
            }
            for e in errors
        ]
    )
    st.dataframe(
        err_df,
        use_container_width=True,
        hide_index=True,
        height=min(400, 40 + len(err_df) * 35),
    )
else:
    st.success("No errors recorded in the audit period.")

st.divider()

# ---------------------------------------------------------------------------
# Row 7 — Anomaly detection
# ---------------------------------------------------------------------------

st.subheader("Latency Anomalies  (> 2× median)")

median_ms = latency.get("p50")
if median_ms:
    threshold = median_ms * 2
    anomalies = [
        e for e in all_entries
        if e.latency_ms is not None
        and e.latency_ms > threshold
        and e.status.value == "success"
    ]
    if anomalies:
        an_df = pd.DataFrame(
            [
                {
                    "Timestamp": e.timestamp[:16].replace("T", " "),
                    "Session": e.session_id,
                    "Provider": e.provider,
                    "Latency (ms)": e.latency_ms,
                    "Prompt (preview)": e.prompt[:80],
                }
                for e in anomalies
            ]
        )
        st.dataframe(an_df, use_container_width=True, hide_index=True)
        st.caption(f"Threshold: {threshold:,}ms  (2× p50 of {median_ms:,}ms)")
    else:
        st.success(f"None detected. All calls within 2× median ({median_ms:,}ms).")
else:
    st.info("Not enough data to calculate anomaly threshold.")

st.caption("AI Decision Audit Log — governance primitive for LLM agents")
