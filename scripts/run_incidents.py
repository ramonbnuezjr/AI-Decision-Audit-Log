"""ServiceNow incident runner for the AI Decision Audit Log POC.

Reads a ServiceNow incident export (JSON or CSV) and runs five AI analysis
prompts on each ticket through the AuditLogger pipeline.  Each ticket becomes
one session; each prompt is one logged call.

Prompt templates (applied per ticket):
    1. summarize      — 2-sentence summary
    2. root_cause     — likely root cause
    3. priority_check — validate priority assignment
    4. remediation    — 3 specific remediation steps
    5. escalation     — escalation recommendation + who to notify

Usage::

    # Dry-run: print prompts without calling the model
    python scripts/run_incidents.py --input scripts/sample_incidents.json --dry-run

    # Run all tickets through local Llama 3.2 3B (default)
    python scripts/run_incidents.py --input data/incidents.json

    # Run first 3 tickets only
    python scripts/run_incidents.py --input data/incidents.json --limit 3

    # Run through OpenAI for cost/quality comparison
    python scripts/run_incidents.py --input data/incidents.json --provider openai

    # Use a specific user ID for audit attribution
    python scripts/run_incidents.py --input data/incidents.json --user-id analyst-team
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES: list[tuple[str, str]] = [
    (
        "summarize",
        (
            "You are an IT operations analyst. Summarize the following incident "
            "ticket in exactly 2 sentences. Be specific about what failed and "
            "what the business impact was.\n\nIncident: {number}\n"
            "Description: {short_description}\n\nDetails: {description}"
        ),
    ),
    (
        "root_cause",
        (
            "You are a root cause analysis expert. Based on the incident below, "
            "identify the single most likely root cause in 2–3 sentences.\n\n"
            "Incident: {number}\nDescription: {short_description}\n\n"
            "Details: {description}"
        ),
    ),
    (
        "priority_check",
        (
            "You are an incident management specialist. The following ticket is "
            "assigned priority '{priority}'. Evaluate whether this priority is "
            "correct given the description. Respond with: correct / too high / "
            "too low, and explain why in 2 sentences.\n\n"
            "Incident: {number}\nDescription: {short_description}\n\n"
            "Details: {description}"
        ),
    ),
    (
        "remediation",
        (
            "You are an IT remediation expert. Provide exactly 3 specific, "
            "actionable remediation steps for the following incident. Number "
            "each step.\n\nIncident: {number}\nDescription: {short_description}"
            "\n\nDetails: {description}"
        ),
    ),
    (
        "escalation",
        (
            "You are an IT escalation coordinator. Based on this incident, "
            "should it be escalated beyond the current assignment group "
            "'{assignment_group}'? Answer yes or no, name who should be "
            "notified, and give one sentence of justification.\n\n"
            "Incident: {number}\nDescription: {short_description}\n\n"
            "Details: {description}"
        ),
    ),
]

# ---------------------------------------------------------------------------
# Ticket loading
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {"number", "short_description"}
_OPTIONAL_FIELDS = {
    "description": "",
    "priority": "3 - Moderate",
    "assignment_group": "IT Operations",
    "category": "Software",
    "state": "In Progress",
}


def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply defaults for optional fields and validate required ones.

    Args:
        raw: Raw ticket dict from the export file.

    Returns:
        Normalised ticket dict with all required fields present.

    Raises:
        ValueError: If a required field is missing.
    """
    for field in _REQUIRED_FIELDS:
        if not raw.get(field):
            raise ValueError(f"Ticket is missing required field: '{field}'")
    ticket = dict(raw)
    for field, default in _OPTIONAL_FIELDS.items():
        if not ticket.get(field):
            ticket[field] = default
    return ticket


def load_tickets(path: Path) -> list[dict[str, Any]]:
    """Load incident tickets from a JSON or CSV file.

    Supports:
    - JSON array of objects: ``[{"number": "INC001", ...}, ...]``
    - CSV with header row matching ServiceNow export format

    Args:
        path: Path to the input file.

    Returns:
        List of normalised ticket dicts.

    Raises:
        ValueError: If the file extension is unsupported or a ticket is invalid.
        FileNotFoundError: If the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open(encoding="utf-8") as fh:
            raw_list = json.load(fh)
        if not isinstance(raw_list, list):
            raise ValueError("JSON file must contain a top-level array of ticket objects.")
    elif suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            raw_list = list(reader)
    else:
        raise ValueError(f"Unsupported file format: '{suffix}'. Use .json or .csv")

    return [_normalise(t) for t in raw_list]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def build_prompt(template: str, ticket: dict[str, Any]) -> str:
    """Render a prompt template with ticket field values.

    Args:
        template: Template string with ``{field}`` placeholders.
        ticket: Normalised ticket dict.

    Returns:
        Rendered prompt string.
    """
    return template.format(**ticket)


def run_ticket(
    ticket: dict[str, Any],
    *,
    provider: str,
    user_id: str,
    max_tokens: int,
    dry_run: bool,
    pause_seconds: float,
) -> int:
    """Run all 5 prompt templates against a single ticket.

    Args:
        ticket: Normalised ticket dict.
        provider: LLM provider to use.
        user_id: User ID for audit attribution.
        max_tokens: Max completion tokens per call.
        dry_run: If True, print prompts without making model calls.
        pause_seconds: Sleep between calls to avoid rate limiting.

    Returns:
        Number of successful captures (0–5).
    """
    session_id = f"ses-{ticket['number']}"
    successes = 0

    print(f"\n{'─' * 60}")
    print(f"Ticket: {ticket['number']}  |  Session: {session_id}")
    print(f"  {ticket['short_description'][:80]}")
    print(f"{'─' * 60}")

    for name, template in PROMPT_TEMPLATES:
        prompt = build_prompt(template, ticket)

        if dry_run:
            print(f"  [DRY-RUN] {name}: {prompt[:120]}...")
            successes += 1
            continue

        print(f"  Running: {name} ...", end=" ", flush=True)
        try:
            # Import here so the script can be dry-run without the venv active
            from src.agent.agent import Agent
            from src.audit.logger import AuditLogger
            from src.config import get_settings
            from src.db.connection import get_connection
            from src.db.schema import ensure_schema

            settings = get_settings()
            with get_connection(settings.audit_store_path) as conn:
                ensure_schema(conn)
                audit_logger = AuditLogger(conn)

                anthropic_client = None
                openai_client = None

                if provider == "anthropic":
                    import anthropic
                    anthropic_client = anthropic.Anthropic(
                        api_key=settings.anthropic_api_key
                    )
                elif provider == "openai":
                    import openai
                    openai_client = openai.OpenAI(api_key=settings.openai_api_key)

                agent = Agent(
                    audit_logger=audit_logger,
                    settings=settings,
                    anthropic_client=anthropic_client,
                    openai_client=openai_client,
                )
                response = agent.chat(
                    prompt,
                    session_id=session_id,
                    user_id=user_id,
                    provider=provider,
                    max_tokens=max_tokens,
                )

            first_line = response.strip().split("\n")[0][:80]
            print(f"OK  →  {first_line}")
            successes += 1

        except Exception as exc:  # noqa: BLE001
            print(f"ERROR  →  {exc}")

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return successes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for run_incidents.py.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="python scripts/run_incidents.py",
        description="Run ServiceNow incident tickets through the AI audit log.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to incident export file (.json or .csv).",
    )
    parser.add_argument(
        "--provider",
        default="llama_cpp",
        choices=["anthropic", "openai", "llama_cpp"],
        help="LLM provider to use (default: llama_cpp).",
    )
    parser.add_argument(
        "--user-id",
        default="poc-runner",
        help="User ID for audit attribution (default: poc-runner).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Max completion tokens per prompt (default: 256).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N tickets.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.5,
        help="Seconds to sleep between API calls (default: 0.5). Set 0 for local model.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts without calling the model.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the incident runner.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = all tickets processed, 1 = input error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    try:
        tickets = load_tickets(input_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.limit:
        tickets = tickets[: args.limit]

    total = len(tickets)
    print(f"Loaded {total} ticket(s) from {input_path}")
    print(f"Provider: {args.provider}  |  Max tokens: {args.max_tokens}  |  Dry-run: {args.dry_run}")
    print(f"Each ticket → {len(PROMPT_TEMPLATES)} prompts  |  Total calls planned: {total * len(PROMPT_TEMPLATES)}")

    total_success = 0
    for ticket in tickets:
        total_success += run_ticket(
            ticket,
            provider=args.provider,
            user_id=args.user_id,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run,
            pause_seconds=args.pause if args.provider != "llama_cpp" else 0.0,
        )

    total_calls = total * len(PROMPT_TEMPLATES)
    print(f"\n{'=' * 60}")
    print(f"Done.  {total_success}/{total_calls} calls succeeded.")
    print(f"Run 'python -m src.main report' to see the governance report.")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
