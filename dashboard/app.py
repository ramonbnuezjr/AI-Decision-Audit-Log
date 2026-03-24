"""Streamlit governance dashboard — Synthetic Sentinel design.

Run with:
    streamlit run dashboard/app.py

Reads data/audit.db via the existing src/db/query layer.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

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
# Design tokens
# ---------------------------------------------------------------------------

C = {
    "surface":   "#060e20",
    "surf_low":  "#091328",
    "surf_high": "#192540",
    "surf_mid":  "#0d1a30",
    "primary":   "#a7a5ff",
    "secondary": "#53ddfc",
    "error":     "#ff6e84",
    "text":      "#dee5ff",
    "muted":     "#a3aac4",
    "outline":   "#40485d",
}

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Governance · Synthetic Sentinel",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS + font injection  (todo: css-injection)
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');

    /* ── Base surfaces ── */
    html, body, [data-testid="stApp"] {{
        background-color: {C['surface']} !important;
        font-family: 'Inter', sans-serif;
        color: {C['text']};
    }}
    [data-testid="stSidebar"] > div:first-child {{
        background-color: {C['surf_low']} !important;
        border-right: none !important;
    }}
    [data-testid="stSidebar"] {{
        border-right: none !important;
    }}

    /* ── Remove Streamlit chrome ── */
    header[data-testid="stHeader"] {{ background: {C['surface']} !important; }}
    .stDeployButton {{ display: none; }}
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    .stDecoration {{ display: none !important; }}

    /* ── Remove all dividers / borders ── */
    hr {{ display: none !important; }}
    [data-testid="stVerticalBlock"] > div[style*="border"] {{ border: none !important; }}

    /* ── Plotly chart containers ── */
    .js-plotly-plot .plotly .bg {{ fill: {C['surf_high']} !important; }}

    /* ── Refresh button ── */
    .stButton > button {{
        background: transparent !important;
        color: {C['primary']} !important;
        border: 1px solid rgba(64,72,93,0.4) !important;
        border-radius: 2px !important;
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding: 0.4rem 1rem;
        width: 100%;
        transition: border-color 0.15s;
    }}
    .stButton > button:hover {{
        border-color: {C['primary']} !important;
    }}

    /* ── Text input ── */
    .stTextInput > div > div > input {{
        background-color: #000 !important;
        color: {C['text']} !important;
        border: 1px solid rgba(64,72,93,0.3) !important;
        border-radius: 2px !important;
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
    }}
    .stTextInput > div > div > input:focus {{
        border-color: {C['secondary']} !important;
        box-shadow: none !important;
    }}
    label[data-testid="stWidgetLabel"] {{
        color: {C['muted']} !important;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}

    /* ── Scrollbars ── */
    ::-webkit-scrollbar {{ width: 4px; height: 4px; }}
    ::-webkit-scrollbar-track {{ background: {C['surf_low']}; }}
    ::-webkit-scrollbar-thumb {{ background: {C['outline']}; border-radius: 0; }}

    /* ── KPI card grid ── */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin-bottom: 2rem;
    }}
    .kpi-card {{
        background: {C['surf_high']};
        border-radius: 2px;
        padding: 1.4rem 1.6rem 1.2rem;
        position: relative;
        border-bottom: 2px solid {C['primary']};
    }}
    .kpi-label {{
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: {C['muted']};
        margin-bottom: 0.5rem;
    }}
    .kpi-value {{
        font-family: 'Space Grotesk', sans-serif;
        font-size: 3rem;
        font-weight: 700;
        color: {C['text']};
        line-height: 1;
        margin-bottom: 0.5rem;
    }}
    .kpi-sub {{
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        color: {C['muted']};
        margin-top: 0.3rem;
    }}
    .kpi-badge-error {{
        display: inline-block;
        background: {C['error']};
        color: #fff;
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        padding: 0.15rem 0.4rem;
        border-radius: 2px;
        vertical-align: middle;
        margin-left: 0.4rem;
    }}
    .kpi-bar {{
        height: 2px;
        background: linear-gradient(135deg, {C['primary']}, {C['secondary']});
        margin-top: 0.8rem;
        border-radius: 1px;
    }}

    /* ── Section headers ── */
    .section-title {{
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.1rem;
        font-weight: 600;
        color: {C['primary']};
        letter-spacing: 0.04em;
        margin: 1.8rem 0 1rem;
    }}

    /* ── Provider pip rows ── */
    .pip-container {{
        background: {C['surf_high']};
        border-radius: 2px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.6rem;
    }}
    .pip-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.6rem;
    }}
    .pip-name {{
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 500;
        color: {C['text']};
        min-width: 90px;
    }}
    .pip-tiles {{
        display: flex;
        flex-wrap: wrap;
        gap: 3px;
        flex: 1;
        margin: 0 1rem;
    }}
    .pip-ok  {{ width: 9px; height: 9px; background: {C['secondary']}; border-radius: 1px; flex-shrink: 0; }}
    .pip-err {{ width: 9px; height: 9px; background: {C['error']};     border-radius: 1px; flex-shrink: 0; }}
    .badge-active  {{
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: {C['secondary']};
        border: 1px solid {C['secondary']};
        padding: 0.1rem 0.4rem;
        border-radius: 2px;
        white-space: nowrap;
    }}
    .badge-blocked {{
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: {C['error']};
        border: 1px solid {C['error']};
        padding: 0.1rem 0.4rem;
        border-radius: 2px;
        white-space: nowrap;
    }}
    .badge-partial {{
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: #f59e0b;
        border: 1px solid #f59e0b;
        padding: 0.1rem 0.4rem;
        border-radius: 2px;
        white-space: nowrap;
    }}

    /* ── Session table ── */
    .ss-table {{
        background: {C['surf_high']};
        border-radius: 2px;
        overflow: hidden;
        width: 100%;
        border-collapse: collapse;
    }}
    .ss-table thead tr {{
        background: {C['surf_mid']};
    }}
    .ss-table thead th {{
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: {C['muted']};
        padding: 0.6rem 1rem;
        text-align: left;
        border: none;
    }}
    .ss-table tbody tr {{
        border-top: 1px solid rgba(64,72,93,0.12);
    }}
    .ss-table tbody tr:nth-child(even) {{
        background: {C['surf_mid']};
    }}
    .ss-table tbody tr:nth-child(odd) {{
        background: {C['surf_high']};
    }}
    .ss-table tbody td {{
        font-family: 'Inter', sans-serif;
        font-size: 0.72rem;
        color: {C['text']};
        padding: 0.55rem 1rem;
        border: none;
    }}
    .ss-table .mono {{
        font-family: 'Space Grotesk', monospace;
        color: {C['muted']};
        font-size: 0.68rem;
    }}
    .ss-table .latency-ok {{
        color: {C['secondary']};
        font-weight: 600;
    }}
    .ss-table .err-badge {{
        color: {C['error']};
        font-weight: 600;
    }}

    /* ── Incident cards ── */
    .incident-card {{
        background: {C['surf_high']};
        border-radius: 2px;
        border-left: 3px solid {C['error']};
        padding: 0.9rem 1.2rem;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
    }}
    .incident-code {{
        font-family: 'Space Grotesk', sans-serif;
        font-size: 0.7rem;
        font-weight: 700;
        color: {C['error']};
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
    }}
    .incident-msg {{
        font-family: 'Inter', sans-serif;
        font-size: 0.72rem;
        color: {C['muted']};
        line-height: 1.4;
    }}
    .incident-ts {{
        font-family: 'Space Grotesk', monospace;
        font-size: 0.65rem;
        color: {C['muted']};
        white-space: nowrap;
        margin-top: 0.15rem;
        flex-shrink: 0;
    }}
    .incident-provider {{
        display: inline-block;
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: {C['muted']};
        margin-right: 0.5rem;
    }}

    /* ── Page header ── */
    .page-header {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        margin-bottom: 1.5rem;
        padding-bottom: 1.2rem;
        border-bottom: 1px solid rgba(64,72,93,0.15);
    }}
    .page-title {{
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2rem;
        font-weight: 700;
        color: {C['text']};
        margin: 0;
        line-height: 1.1;
    }}
    .page-subtitle {{
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        color: {C['muted']};
        margin-top: 0.3rem;
    }}
    .status-pill-ok {{
        background: rgba(83,221,252,0.1);
        border: 1px solid {C['secondary']};
        color: {C['secondary']};
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 0.3rem 0.8rem;
        border-radius: 2px;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-top: 0.3rem;
    }}
    .status-pill-warn {{
        background: rgba(255,110,132,0.1);
        border: 1px solid {C['error']};
        color: {C['error']};
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 0.3rem 0.8rem;
        border-radius: 2px;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-top: 0.3rem;
    }}
    .status-dot {{
        width: 6px;
        height: 6px;
        border-radius: 50%;
        display: inline-block;
    }}

    /* ── Sidebar brand ── */
    .sidebar-brand {{
        padding: 0.2rem 0 1.2rem;
        border-bottom: 1px solid rgba(64,72,93,0.2);
        margin-bottom: 1rem;
    }}
    .sidebar-brand-title {{
        font-family: 'Space Grotesk', sans-serif;
        font-size: 0.8rem;
        font-weight: 700;
        color: {C['primary']};
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }}
    .sidebar-brand-sub {{
        font-family: 'Inter', sans-serif;
        font-size: 0.62rem;
        color: {C['muted']};
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-top: 0.1rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_code(msg: str) -> str:
    """Extract a short error code label from an error message string."""
    if not msg:
        return "ERROR"
    m = re.search(r"(\d{3})", msg)
    if m:
        code = m.group(1)
        labels = {
            "401": "401 UNAUTHORIZED",
            "403": "403 FORBIDDEN",
            "429": "429 RATE LIMIT EXCEEDED",
            "500": "500 INTERNAL SERVER ERROR",
            "503": "503 SERVICE UNAVAILABLE",
        }
        return labels.get(code, f"{code} ERROR")
    if "quota" in msg.lower():
        return "QUOTA EXCEEDED"
    if "auth" in msg.lower() or "key" in msg.lower():
        return "AUTH FAILURE"
    return "ERROR"


def _plotly_layout(fig: go.Figure, height: int = 260) -> go.Figure:
    """Apply Synthetic Sentinel dark theme to a Plotly figure."""
    fig.update_layout(
        paper_bgcolor=C["surf_high"],
        plot_bgcolor=C["surf_high"],
        font=dict(family="Inter, sans-serif", color=C["muted"], size=11),
        height=height,
        margin=dict(t=16, b=16, l=8, r=8),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=C["muted"], size=10),
        ),
        xaxis=dict(
            gridcolor=f"rgba(64,72,93,0.2)",
            zerolinecolor=f"rgba(64,72,93,0.3)",
            tickfont=dict(color=C["muted"]),
        ),
        yaxis=dict(
            gridcolor=f"rgba(64,72,93,0.2)",
            zerolinecolor=f"rgba(64,72,93,0.3)",
            tickfont=dict(color=C["muted"]),
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# DB path + cache bust
# ---------------------------------------------------------------------------

DB_DEFAULT = str(Path(__file__).resolve().parent.parent / "data" / "audit.db")

if "bust" not in st.session_state:
    st.session_state["bust"] = 0

# ---------------------------------------------------------------------------
# Sidebar  (todo: header-sidebar)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">AI Governance</div>
            <div class="sidebar-brand-sub">Command Center</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    db_path = st.text_input("Database path", value=DB_DEFAULT, label_visibility="visible")

    if st.button("↻  Refresh data"):
        st.session_state["bust"] += 1
        st.cache_data.clear()

    if Path(db_path).exists():
        size_kb = Path(db_path).stat().st_size / 1024
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C["muted"]};margin-top:0.8rem;">'
            f'audit.db &nbsp;·&nbsp; {size_kb:,.0f} KB</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_data(path: str, _bust: int) -> dict:  # noqa: ANN001
    """Load all query results from the SQLite database."""
    with get_connection(path) as conn:
        ensure_schema(conn)
        all_entries = get_all_calls(conn)
        errors      = get_errors(conn)
        health      = get_provider_health(conn)
        latency     = get_latency_stats(conn)
        usage       = get_model_usage_summary(conn)
        sessions    = get_session_activity(conn)
    return {
        "all": all_entries, "errors": errors, "health": health,
        "latency": latency, "usage": usage, "sessions": sessions,
    }

if not Path(db_path).exists():
    st.error(f"No database found at `{db_path}`. Run a capture first.")
    st.stop()

data        = load_data(db_path, st.session_state["bust"])
all_entries = data["all"]
errors      = data["errors"]
health_rows = data["health"]
latency     = data["latency"]
usage_rows  = data["usage"]
session_rows= data["sessions"]

if not all_entries:
    st.info("No entries in the audit log yet.")
    st.stop()

# ---------------------------------------------------------------------------
# Derived aggregates
# ---------------------------------------------------------------------------

total_calls   = len(all_entries)
success_calls = sum(1 for e in all_entries if e.status.value == "success")
success_rate  = round(success_calls / total_calls * 100, 1) if total_calls else 0.0
total_in      = sum(r["total_input_tokens"] for r in usage_rows)
total_out     = sum(r["total_output_tokens"] for r in usage_rows)
total_tokens  = total_in + total_out
cloud_in      = sum(r["total_input_tokens"]  for r in usage_rows if r["provider"] in ("anthropic", "openai"))
cloud_out     = sum(r["total_output_tokens"] for r in usage_rows if r["provider"] in ("anthropic", "openai"))
est_cost      = (cloud_in / 1_000_000 * 2.50) + (cloud_out / 1_000_000 * 10.00)
timestamps    = sorted(e.timestamp for e in all_entries)
period_start  = timestamps[0][:10]
period_end    = timestamps[-1][:10]
error_count   = len(errors)

# ---------------------------------------------------------------------------
# Page header  (todo: header-sidebar)
# ---------------------------------------------------------------------------

if error_count == 0:
    pill = (
        f'<div class="status-pill-ok">'
        f'<span class="status-dot" style="background:{C["secondary"]};"></span>'
        f'Systems Nominal</div>'
    )
else:
    pill = (
        f'<div class="status-pill-warn">'
        f'<span class="status-dot" style="background:{C["error"]};"></span>'
        f'{error_count} Incident{"s" if error_count != 1 else ""} Active</div>'
    )

st.markdown(
    f"""
    <div class="page-header">
        <div>
            <div class="page-title">Oversight Dashboard</div>
            <div class="page-subtitle">
                Real-time governance telemetry &nbsp;·&nbsp;
                {period_start} → {period_end} &nbsp;·&nbsp; {total_calls:,} calls
            </div>
        </div>
        {pill}
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Row 1 — KPI cards  (todo: kpi-cards)
# ---------------------------------------------------------------------------

tokens_display = f"{total_tokens / 1000:.0f}k" if total_tokens >= 1000 else str(total_tokens)
error_badge = (
    f'<span class="kpi-badge-error">{error_count} ERROR{"S" if error_count != 1 else ""}</span>'
    if error_count else ""
)

st.markdown(
    f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Total Calls</div>
            <div class="kpi-value">{total_calls:,}{error_badge}</div>
            <div class="kpi-sub">{success_calls:,} succeeded &nbsp;·&nbsp; {error_count} failed</div>
            <div class="kpi-bar"></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Success Rate</div>
            <div class="kpi-value">{success_rate}%</div>
            <div class="kpi-sub">across all providers</div>
            <div class="kpi-bar"></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Tokens</div>
            <div class="kpi-value">{tokens_display}</div>
            <div class="kpi-sub">{total_in:,} in &nbsp;/&nbsp; {total_out:,} out</div>
            <div class="kpi-bar"></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Estimated Cost</div>
            <div class="kpi-value">${est_cost:.4f}</div>
            <div class="kpi-sub">GPT-4o cloud pricing</div>
            <div class="kpi-bar"></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Row 2 — Provider Health pips  (todo: provider-health)
# ---------------------------------------------------------------------------

st.markdown('<div class="section-title">Provider Health</div>', unsafe_allow_html=True)

pip_rows_html = ""
for row in health_rows:
    ok_count  = row["success_calls"]
    err_count = row["error_calls"]
    rate      = row["success_rate"]

    pips = "".join(['<div class="pip-ok"></div>']  * min(ok_count,  120))
    pips += "".join(['<div class="pip-err"></div>'] * min(err_count, 120))

    if rate == 100.0:
        badge = f'<span class="badge-active">Active</span>'
    elif rate == 0.0:
        badge = f'<span class="badge-blocked">Blocked</span>'
    else:
        badge = f'<span class="badge-partial">{rate:.0f}% OK</span>'

    pip_rows_html += f"""
        <div class="pip-row">
            <div class="pip-name">{row['provider']}</div>
            <div class="pip-tiles">{pips}</div>
            {badge}
        </div>
    """

st.markdown(
    f'<div class="pip-container">{pip_rows_html}</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Row 3 — Latency profile  +  Token burn  (todo: charts-reskin)
# ---------------------------------------------------------------------------

st.markdown('<div class="section-title">Latency Profile (ms) &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Token Burn</div>', unsafe_allow_html=True)
col_lat, col_tok = st.columns(2)

with col_lat:
    if latency["count"]:
        lat_df = pd.DataFrame({
            "Metric": ["P50 Median", "P95 Tail", "MAX Spike"],
            "ms":     [latency["p50"], latency["p95"], latency["max"]],
        })
        fig_lat = go.Figure()
        bar_colors = [C["secondary"], C["primary"], C["error"]]
        for i, (_, r) in enumerate(lat_df.iterrows()):
            fig_lat.add_trace(go.Bar(
                x=[r["ms"]], y=[r["Metric"]],
                orientation="h",
                marker_color=bar_colors[i],
                text=[f"{r['ms']:,}ms"],
                textposition="outside",
                textfont=dict(color=C["muted"], size=10),
                showlegend=False,
                name=r["Metric"],
            ))
        fig_lat.update_layout(
            paper_bgcolor=C["surf_high"],
            plot_bgcolor=C["surf_high"],
            height=220,
            margin=dict(t=8, b=8, l=8, r=60),
            barmode="overlay",
            xaxis=dict(
                visible=False,
                range=[0, latency["max"] * 1.35],
            ),
            yaxis=dict(
                tickfont=dict(color=C["text"], size=11, family="Inter"),
                gridcolor="rgba(0,0,0,0)",
                ticksuffix="  ",
            ),
            font=dict(family="Inter", color=C["muted"]),
        )
        st.plotly_chart(fig_lat, use_container_width=True)
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C["muted"]};margin-top:-0.5rem;">'
            f'{latency["count"]:,} successful calls &nbsp;·&nbsp; min {latency["min"]:,}ms</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No successful calls yet.")

with col_tok:
    tok_df = pd.DataFrame([
        {"provider": r["provider"],
         "tokens": r["total_input_tokens"] + r["total_output_tokens"]}
        for r in usage_rows if (r["total_input_tokens"] + r["total_output_tokens"]) > 0
    ])
    if not tok_df.empty:
        tok_colors = [C["primary"], C["secondary"], C["error"], "#f59e0b"]
        fig_tok = go.Figure(go.Pie(
            labels=tok_df["provider"],
            values=tok_df["tokens"],
            hole=0.58,
            marker=dict(colors=tok_colors[:len(tok_df)], line=dict(width=0)),
            textinfo="label+percent",
            textfont=dict(color=C["muted"], size=10, family="Inter"),
            insidetextorientation="horizontal",
        ))
        fig_tok.update_layout(
            paper_bgcolor=C["surf_high"],
            plot_bgcolor=C["surf_high"],
            height=220,
            margin=dict(t=8, b=8, l=8, r=8),
            showlegend=True,
            legend=dict(
                font=dict(color=C["muted"], size=10, family="Inter"),
                bgcolor="rgba(0,0,0,0)",
                x=0.75, y=0.5,
                xanchor="left",
            ),
            font=dict(family="Inter"),
            annotations=[dict(
                text=f"{total_tokens // 1000}k",
                x=0.38, y=0.5,
                font=dict(family="Space Grotesk", size=22, color=C["text"]),
                showarrow=False,
            )],
        )
        st.plotly_chart(fig_tok, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 4 — Calls over time  (todo: charts-reskin)
# ---------------------------------------------------------------------------

st.markdown('<div class="section-title">Calls Over Time</div>', unsafe_allow_html=True)

ts_series = pd.to_datetime([e.timestamp for e in all_entries])
ts_df     = pd.DataFrame({"timestamp": ts_series})
ts_df["hour"] = ts_df["timestamp"].dt.floor("h")
hourly = ts_df.groupby("hour").size().reset_index(name="calls")

if len(hourly) > 1:
    fig_ts = go.Figure(go.Scatter(
        x=hourly["hour"], y=hourly["calls"],
        mode="lines+markers",
        line=dict(color=C["secondary"], width=2),
        marker=dict(color=C["primary"], size=5),
        fill="tozeroy",
        fillcolor=f"rgba(83,221,252,0.06)",
    ))
else:
    fig_ts = go.Figure(go.Bar(
        x=hourly["hour"], y=hourly["calls"],
        marker_color=C["secondary"],
    ))

_plotly_layout(fig_ts, height=200)
fig_ts.update_layout(showlegend=False)
st.plotly_chart(fig_ts, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 5 — Session activity table  (todo: session-table)
# ---------------------------------------------------------------------------

st.markdown('<div class="section-title">Session Activity</div>', unsafe_allow_html=True)

rows_html = ""
for row in session_rows[:20]:
    sid       = row["session_id"]
    calls     = row["total_calls"]
    provider  = row.get("user_id", "—")
    first     = row["first_call"][11:16] if row["first_call"] else "—"
    latency_s = "—"
    errs      = row["error_calls"]
    err_html  = f'<span class="err-badge">{errs}</span>' if errs else "0"

    rows_html += f"""
    <tr>
        <td class="mono">{sid[:28]}{'…' if len(sid) > 28 else ''}</td>
        <td>{provider}</td>
        <td class="latency-ok">{first}</td>
        <td>{calls}</td>
        <td>{err_html}</td>
    </tr>
    """

st.markdown(
    f"""
    <table class="ss-table">
        <thead>
            <tr>
                <th>Session ID</th>
                <th>User</th>
                <th>First Call</th>
                <th>Calls</th>
                <th>Errors</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Row 6 — Incident cards  (todo: incident-cards)
# ---------------------------------------------------------------------------

st.markdown(
    f'<div class="section-title">Incident Log'
    f'<span style="margin-left:1rem;font-size:0.65rem;color:{C["error"] if errors else C["secondary"]};">'
    f'● {"  " + str(len(errors)) + " Active" if errors else "  Clear"}</span></div>',
    unsafe_allow_html=True,
)

if errors:
    cards_html = ""
    for e in errors[:15]:
        code    = _error_code(e.error_message or "")
        msg     = (e.error_message or "")[:160]
        ts      = e.timestamp[11:19]
        session = e.session_id[:22] + ("…" if len(e.session_id) > 22 else "")
        cards_html += f"""
        <div class="incident-card">
            <div>
                <div class="incident-code">{code}</div>
                <div class="incident-msg">
                    <span class="incident-provider">{e.provider}</span>{msg}
                </div>
            </div>
            <div style="text-align:right;">
                <div class="incident-ts">{ts}</div>
                <div class="incident-ts" style="margin-top:0.2rem;font-size:0.6rem;">{session}</div>
            </div>
        </div>
        """
    st.markdown(cards_html, unsafe_allow_html=True)
    if len(errors) > 15:
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C["muted"]};margin-top:0.4rem;">'
            f'… and {len(errors) - 15} more</div>',
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        f'<div style="background:{C["surf_high"]};border-radius:2px;border-left:3px solid {C["secondary"]};'
        f'padding:0.9rem 1.2rem;font-family:Inter;font-size:0.75rem;color:{C["secondary"]};">'
        f'No errors recorded in the audit period.</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Row 7 — Anomaly detection
# ---------------------------------------------------------------------------

median_ms = latency.get("p50")
if median_ms:
    threshold = median_ms * 2
    anomalies = [
        e for e in all_entries
        if e.latency_ms is not None and e.latency_ms > threshold
        and e.status.value == "success"
    ]
    if anomalies:
        st.markdown('<div class="section-title">Latency Anomalies</div>', unsafe_allow_html=True)
        an_html = ""
        for e in anomalies[:8]:
            an_html += f"""
            <div class="incident-card" style="border-left-color:{C['primary']}">
                <div>
                    <div class="incident-code" style="color:{C['primary']}">LATENCY SPIKE</div>
                    <div class="incident-msg">
                        <span class="incident-provider">{e.provider}</span>
                        {e.prompt[:80]}…
                    </div>
                </div>
                <div style="text-align:right;">
                    <div class="incident-ts" style="color:{C['primary']};font-weight:700;">{e.latency_ms:,}ms</div>
                    <div class="incident-ts">{e.session_id[:22]}</div>
                </div>
            </div>
            """
        st.markdown(an_html, unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C["muted"]};margin-top:0.3rem;">'
            f'Threshold: {threshold:,}ms &nbsp;(2× p50 of {median_ms:,}ms)</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    f'<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid rgba(64,72,93,0.15);'
    f'font-family:Inter;font-size:0.62rem;color:{C["muted"]};letter-spacing:0.06em;">'
    f'AI DECISION AUDIT LOG &nbsp;·&nbsp; GOVERNANCE PRIMITIVE &nbsp;·&nbsp; '
    f'<a href="https://github.com/ramonbnuezjr/AI-Decision-Audit-Log" '
    f'style="color:{C["muted"]};text-decoration:none;">github.com/ramonbnuezjr</a></div>',
    unsafe_allow_html=True,
)
