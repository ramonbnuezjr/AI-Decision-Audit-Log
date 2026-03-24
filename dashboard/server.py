"""FastAPI server for the AI Governance Sentinel Dashboard.

Serves two routes:
    GET /          — the index.html frontend
    GET /api/data  — all audit log data as a single JSON payload

Run with:
    uvicorn dashboard.server:app --reload --port 8000
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

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

_HERE = Path(__file__).resolve().parent
_DB   = _HERE.parent / "data" / "audit.db"

app = FastAPI(title="AI Governance Sentinel", docs_url=None, redoc_url=None)


@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    """Serve the Sentinel dashboard HTML."""
    return FileResponse(_HERE / "index.html", media_type="text/html")


@app.get("/api/data")
def get_data() -> JSONResponse:
    """Return all governance metrics as a single JSON payload."""
    with get_connection(str(_DB)) as conn:
        ensure_schema(conn)
        all_entries  = get_all_calls(conn)
        errors       = get_errors(conn)
        health_rows  = get_provider_health(conn)
        latency      = get_latency_stats(conn)
        usage_rows   = get_model_usage_summary(conn)
        session_rows = get_session_activity(conn)

    if not all_entries:
        return JSONResponse({"empty": True})

    # ── Summary aggregates ──────────────────────────────────────────────────
    total_calls   = len(all_entries)
    success_calls = sum(1 for e in all_entries if e.status.value == "success")
    success_rate  = round(success_calls / total_calls * 100, 1) if total_calls else 0.0
    total_in      = sum(r["total_input_tokens"]  for r in usage_rows)
    total_out     = sum(r["total_output_tokens"] for r in usage_rows)
    total_tokens  = total_in + total_out
    cloud_in      = sum(r["total_input_tokens"]  for r in usage_rows if r["provider"] in ("anthropic", "openai"))
    cloud_out     = sum(r["total_output_tokens"] for r in usage_rows if r["provider"] in ("anthropic", "openai"))
    est_cost      = (cloud_in / 1_000_000 * 2.50) + (cloud_out / 1_000_000 * 10.00)
    timestamps    = sorted(e.timestamp for e in all_entries)

    # ── Calls per hour timeline ─────────────────────────────────────────────
    hourly: Counter[str] = Counter()
    for e in all_entries:
        hourly[e.timestamp[:13]] += 1  # "2026-03-23T00"
    timeline = [{"hour": h, "calls": c} for h, c in sorted(hourly.items())]

    # ── Error list ──────────────────────────────────────────────────────────
    error_list = [
        {
            "timestamp":     e.timestamp,
            "provider":      e.provider,
            "session_id":    e.session_id,
            "error_message": e.error_message or "",
        }
        for e in errors
    ]

    return JSONResponse({
        "summary": {
            "total_calls":   total_calls,
            "success_calls": success_calls,
            "success_rate":  success_rate,
            "total_tokens":  total_tokens,
            "total_in":      total_in,
            "total_out":     total_out,
            "est_cost":      round(est_cost, 6),
            "period_start":  timestamps[0][:10],
            "period_end":    timestamps[-1][:10],
            "error_count":   len(errors),
        },
        "health":   health_rows,
        "latency":  latency,
        "usage":    usage_rows,
        "sessions": session_rows,
        "errors":   error_list,
        "timeline": timeline,
    })
