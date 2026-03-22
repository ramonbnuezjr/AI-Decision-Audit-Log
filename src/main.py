"""CLI entrypoint for ai-decision-audit-log.

Commands::

    # Send a prompt through the audit log
    python -m src.main capture \\
        --prompt "Explain transformer architecture" \\
        --provider anthropic \\
        --session-id ses-001 \\
        --user-id user-001

    # Query the audit log
    python -m src.main query --session-id ses-001
    python -m src.main query --user-id user-001
    python -m src.main query --errors-only

    # Export entries to JSON
    python -m src.main export --format json --output ./audit_export.json

    # Show model usage summary
    python -m src.main summary
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

import structlog

from src.config import get_settings
from src.db.connection import get_connection
from src.db.query import (
    get_all_calls,
    get_by_session,
    get_by_user,
    get_errors,
    get_latency_stats,
    get_model_usage_summary,
    get_provider_health,
    get_session_activity,
)
from src.db.schema import ensure_schema

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _configure_logging(level: str) -> None:
    """Configure structlog with a simple timestamped console renderer.

    Args:
        level: One of DEBUG | INFO | WARNING | ERROR.
    """
    import logging

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )


def _entries_to_dicts(entries: list[Any]) -> list[dict[str, Any]]:
    """Serialise LogEntry objects to plain dicts for JSON output.

    Args:
        entries: List of LogEntry instances.

    Returns:
        List of dicts with all fields, status as string.
    """
    return [e.model_dump() for e in entries]


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_capture(args: argparse.Namespace) -> int:
    """Execute the ``capture`` subcommand — send a prompt and log the result.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    settings = get_settings()
    session_id = args.session_id or str(uuid.uuid4())
    user_id = args.user_id or "cli-user"

    with get_connection(settings.audit_store_path) as conn:
        ensure_schema(conn)

        from src.agent.agent import Agent
        from src.audit.logger import AuditLogger

        audit_logger = AuditLogger(conn)

        anthropic_client = None
        openai_client = None

        if args.provider == "anthropic":
            if not settings.anthropic_api_key:
                print(
                    "ERROR: ANTHROPIC_API_KEY is not set in environment.",
                    file=sys.stderr,
                )
                return 1
            import anthropic

            anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        elif args.provider == "openai":
            if not settings.openai_api_key:
                print(
                    "ERROR: OPENAI_API_KEY is not set in environment.",
                    file=sys.stderr,
                )
                return 1
            import openai

            openai_client = openai.OpenAI(api_key=settings.openai_api_key)

        agent = Agent(
            audit_logger=audit_logger,
            settings=settings,
            anthropic_client=anthropic_client,
            openai_client=openai_client,
        )

        try:
            response = agent.chat(
                args.prompt,
                session_id=session_id,
                user_id=user_id,
                provider=args.provider,
                max_tokens=args.max_tokens,
            )
        except Exception as exc:  # broad catch: surface provider errors cleanly
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        print(response)
        print(
            f"\n[Logged] session={session_id} user={user_id} provider={args.provider}",
            file=sys.stderr,
        )
        return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Execute the ``query`` subcommand — retrieve audit entries.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code (0 = success).
    """
    settings = get_settings()

    with get_connection(settings.audit_store_path) as conn:
        ensure_schema(conn)

        if args.session_id:
            entries = get_by_session(conn, args.session_id)
        elif args.user_id:
            entries = get_by_user(conn, args.user_id)
        elif args.errors_only:
            entries = get_errors(conn)
        else:
            entries = get_all_calls(conn)

    if not entries:
        print("No entries found.")
        return 0

    for entry in entries:
        print(
            f"[{entry.timestamp}] {entry.provider}/{entry.model} "
            f"status={entry.status.value} "
            f"latency={entry.latency_ms}ms "
            f"session={entry.session_id}"
        )
        print(f"  PROMPT : {entry.prompt[:120]}")
        if entry.response:
            print(f"  RESPONSE: {entry.response[:120]}")
        if entry.error_message:
            print(f"  ERROR  : {entry.error_message}")
        print()

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Execute the ``export`` subcommand — write entries to a file.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    settings = get_settings()

    with get_connection(settings.audit_store_path) as conn:
        ensure_schema(conn)
        entries = get_all_calls(conn)

    if args.format == "json":
        data = _entries_to_dicts(entries)
        output = json.dumps(data, indent=2, default=str)
    else:
        print(f"ERROR: unsupported format {args.format!r}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Exported {len(entries)} entries to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


def cmd_summary(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Execute the ``summary`` subcommand — print model usage table.

    Args:
        args: Parsed argument namespace (unused).

    Returns:
        Exit code (0 = success).
    """
    settings = get_settings()

    with get_connection(settings.audit_store_path) as conn:
        ensure_schema(conn)
        rows = get_model_usage_summary(conn)

    if not rows:
        print("No entries in audit log yet.")
        return 0

    header = (
        f"{'PROVIDER':<12} {'MODEL':<35} {'CALLS':>6} "
        f"{'OK':>6} {'ERR':>6} {'IN TOK':>10} {'OUT TOK':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['provider']:<12} {row['model']:<35} {row['total_calls']:>6} "
            f"{row['successful_calls']:>6} {row['error_calls']:>6} "
            f"{row['total_input_tokens']:>10} {row['total_output_tokens']:>10}"
        )

    return 0


def cmd_report(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Execute the ``report`` subcommand — print a governance summary.

    Surfaces provider health, error incidents, latency profile, token burn,
    session activity, and latency anomalies in a single structured output.

    Args:
        args: Parsed argument namespace (unused).

    Returns:
        Exit code (0 = success).
    """
    settings = get_settings()

    with get_connection(settings.audit_store_path) as conn:
        ensure_schema(conn)
        health_rows = get_provider_health(conn)
        error_entries = get_errors(conn)
        latency = get_latency_stats(conn)
        usage_rows = get_model_usage_summary(conn)
        session_rows = get_session_activity(conn)
        all_entries = get_all_calls(conn)

    if not all_entries:
        print("No entries in audit log yet.")
        return 0

    total_calls = len(all_entries)
    timestamps = sorted(e.timestamp for e in all_entries)
    period_start = timestamps[0][:10]
    period_end = timestamps[-1][:10]

    print(f"\n{'=' * 60}")
    print(f"  AI GOVERNANCE REPORT")
    print(f"  Period: {period_start} \u2192 {period_end}  |  Total calls: {total_calls}")
    print(f"{'=' * 60}")

    # -- Incident log --------------------------------------------------------
    print(f"\nINCIDENT LOG  ({len(error_entries)} error{'s' if len(error_entries) != 1 else ''})")
    if not error_entries:
        print("  No errors recorded.")
    else:
        for e in error_entries[:10]:
            ts = e.timestamp[:16].replace("T", " ")
            msg = (e.error_message or "")[:60]
            print(f"  [{ts}] {e.provider:<12} {msg}  {e.session_id}")
        if len(error_entries) > 10:
            print(f"  ... and {len(error_entries) - 10} more (run: query --errors-only)")

    # -- Provider health -----------------------------------------------------
    print("\nPROVIDER HEALTH")
    for row in health_rows:
        rate = row["success_rate"]
        indicator = "" if rate == 100.0 else (" \u2190 investigate" if rate > 0 else " \u2190 BLOCKED")
        print(
            f"  {row['provider']:<14} {rate:>5.1f}% success"
            f"  ({row['success_calls']}/{row['total_calls']}){indicator}"
        )

    # -- Latency profile -----------------------------------------------------
    print("\nLATENCY PROFILE  (successful calls only)")
    if latency["count"] == 0:
        print("  No successful calls recorded.")
    else:
        print(
            f"  p50: {latency['p50']:>7,}ms   "
            f"p95: {latency['p95']:>7,}ms   "
            f"max: {latency['max']:>7,}ms"
        )

    # -- Token burn ----------------------------------------------------------
    total_in = sum(r["total_input_tokens"] for r in usage_rows)
    total_out = sum(r["total_output_tokens"] for r in usage_rows)
    cloud_calls = sum(
        r["successful_calls"] for r in usage_rows if r["provider"] in ("anthropic", "openai")
    )
    cloud_in = sum(
        r["total_input_tokens"] for r in usage_rows if r["provider"] in ("anthropic", "openai")
    )
    cloud_out = sum(
        r["total_output_tokens"] for r in usage_rows if r["provider"] in ("anthropic", "openai")
    )
    # GPT-4o pricing: $2.50/1M input, $10.00/1M output (as of 2026-03)
    est_cost = (cloud_in / 1_000_000 * 2.50) + (cloud_out / 1_000_000 * 10.00)
    print(f"\nTOKEN BURN")
    print(f"  Input:  {total_in:>8,} tokens   Output: {total_out:>8,} tokens")
    if cloud_calls:
        print(f"  GPT-4o est. cost ({cloud_calls} cloud calls): ${est_cost:.4f}")
    else:
        print("  No cloud API calls — all runs used local model (cost: $0.00)")

    # -- Session activity ----------------------------------------------------
    top_n = 8
    print(f"\nSESSION ACTIVITY  (top {min(top_n, len(session_rows))} of {len(session_rows)})")
    for row in session_rows[:top_n]:
        err_flag = f"  \u2190 {row['error_calls']} error{'s' if row['error_calls'] != 1 else ''}" if row["error_calls"] else ""
        first = row["first_call"][:16].replace("T", " ")
        last = row["last_call"][:16].replace("T", " ")
        print(
            f"  {row['session_id']:<30} {row['total_calls']:>3} calls"
            f"  {row['user_id']:<12} {first} \u2192 {last}{err_flag}"
        )

    # -- Anomalies -----------------------------------------------------------
    median_latency = latency.get("p50")
    anomalies = []
    if median_latency:
        threshold = median_latency * 2
        anomalies = [
            e for e in all_entries
            if e.latency_ms is not None and e.latency_ms > threshold
            and e.status.value == "success"
        ]
    print(f"\nANOMALIES  (latency > 2\u00d7 median)")
    if not anomalies:
        print("  None detected.")
    else:
        for e in anomalies[:5]:
            ts = e.timestamp[:16].replace("T", " ")
            print(f"  [{ts}] {e.session_id}  {e.latency_ms:,}ms  ({e.provider})")
        if len(anomalies) > 5:
            print(f"  ... and {len(anomalies) - 5} more")

    print(f"\n{'=' * 60}\n")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser.

    Returns:
        Configured ArgumentParser with all subcommands registered.
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="ai-decision-audit-log — governance primitive for LLM agents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- capture -------------------------------------------------------------
    cap = subparsers.add_parser("capture", help="Send a prompt and log the result.")
    cap.add_argument("--prompt", required=True, help="Prompt text to send.")
    cap.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "openai", "llama_cpp"],
        help="LLM provider to use (default: anthropic).",
    )
    cap.add_argument("--session-id", default=None, help="Session ID (auto-generated if omitted).")
    cap.add_argument("--user-id", default="cli-user", help="User ID (default: cli-user).")
    cap.add_argument("--max-tokens", type=int, default=1024, help="Max completion tokens.")

    # -- query ---------------------------------------------------------------
    qry = subparsers.add_parser("query", help="Query the audit log.")
    qry_group = qry.add_mutually_exclusive_group()
    qry_group.add_argument("--session-id", default=None, help="Filter by session ID.")
    qry_group.add_argument("--user-id", default=None, help="Filter by user ID.")
    qry_group.add_argument(
        "--errors-only", action="store_true", help="Show only error/flagged entries."
    )

    # -- export --------------------------------------------------------------
    exp = subparsers.add_parser("export", help="Export audit log to file.")
    exp.add_argument(
        "--format", default="json", choices=["json"], help="Output format (default: json)."
    )
    exp.add_argument("--output", default=None, help="Output file path (stdout if omitted).")

    # -- summary -------------------------------------------------------------
    subparsers.add_parser("summary", help="Print model usage summary.")

    # -- report --------------------------------------------------------------
    subparsers.add_parser("report", help="Print full governance report (incidents, latency, cost, anomalies).")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code.
    """
    settings = get_settings()
    _configure_logging(settings.log_level)

    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "capture": cmd_capture,
        "query": cmd_query,
        "export": cmd_export,
        "summary": cmd_summary,
        "report": cmd_report,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
