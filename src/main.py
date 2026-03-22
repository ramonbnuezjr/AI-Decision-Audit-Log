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
    get_model_usage_summary,
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
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
