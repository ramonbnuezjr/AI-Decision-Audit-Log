"""Query utilities for the audit_log SQLite table."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.models.log_entry import LogEntry


def _percentile(values: list[int], pct: float) -> int:
    """Return the value at the given percentile from a sorted list.

    Uses nearest-rank method.  Caller must ensure list is sorted ascending
    and non-empty.

    Args:
        values: Sorted list of integers.
        pct: Percentile in the range [0, 100].

    Returns:
        The value at the requested percentile.
    """
    idx = max(0, int(len(values) * pct / 100) - 1)
    return values[min(idx, len(values) - 1)]


def _rows_to_entries(rows: list[sqlite3.Row]) -> list[LogEntry]:
    """Convert a list of sqlite3.Row objects to LogEntry instances.

    Args:
        rows: Rows returned by a sqlite3 cursor.

    Returns:
        List of validated LogEntry objects.
    """
    return [LogEntry.from_sqlite_row(tuple(row)) for row in rows]


def get_all_calls(conn: sqlite3.Connection) -> list[LogEntry]:
    """Return every audit log entry, most recent first.

    Args:
        conn: Open sqlite3.Connection with the audit_log table present.

    Returns:
        All LogEntry records ordered by timestamp descending.
    """
    cursor = conn.execute(
        "SELECT * FROM audit_log ORDER BY timestamp DESC"
    )
    return _rows_to_entries(cursor.fetchall())


def get_by_session(conn: sqlite3.Connection, session_id: str) -> list[LogEntry]:
    """Reconstruct a conversation by returning all calls for a session.

    Args:
        conn: Open sqlite3.Connection.
        session_id: Session identifier to filter on.

    Returns:
        LogEntry records for the session, ordered by timestamp ascending
        (chronological order for conversation replay).
    """
    cursor = conn.execute(
        "SELECT * FROM audit_log WHERE session_id = ? ORDER BY timestamp ASC",
        (session_id,),
    )
    return _rows_to_entries(cursor.fetchall())


def get_by_user(conn: sqlite3.Connection, user_id: str) -> list[LogEntry]:
    """Return all calls made by a specific user, most recent first.

    Args:
        conn: Open sqlite3.Connection.
        user_id: User identifier to filter on.

    Returns:
        LogEntry records for the user, ordered by timestamp descending.
    """
    cursor = conn.execute(
        "SELECT * FROM audit_log WHERE user_id = ? ORDER BY timestamp DESC",
        (user_id,),
    )
    return _rows_to_entries(cursor.fetchall())


def get_errors(conn: sqlite3.Connection) -> list[LogEntry]:
    """Return all failed or flagged calls, most recent first.

    Args:
        conn: Open sqlite3.Connection.

    Returns:
        LogEntry records with status ``error`` or ``flagged``.
    """
    cursor = conn.execute(
        "SELECT * FROM audit_log WHERE status IN ('error', 'flagged') "
        "ORDER BY timestamp DESC"
    )
    return _rows_to_entries(cursor.fetchall())


def get_model_usage_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return a usage summary grouped by provider and model.

    Columns returned:
        - ``provider``: provider name
        - ``model``: model identifier
        - ``total_calls``: number of calls
        - ``successful_calls``: calls with status ``success``
        - ``error_calls``: calls with status ``error`` or ``flagged``
        - ``total_input_tokens``: sum of input_tokens (NULL treated as 0)
        - ``total_output_tokens``: sum of output_tokens (NULL treated as 0)

    Args:
        conn: Open sqlite3.Connection.

    Returns:
        List of dicts, one per (provider, model) combination, ordered by
        total_calls descending.
    """
    cursor = conn.execute(
        """
        SELECT
            provider,
            model,
            COUNT(*)                                           AS total_calls,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successful_calls,
            SUM(CASE WHEN status IN ('error', 'flagged') THEN 1 ELSE 0 END)
                                                               AS error_calls,
            COALESCE(SUM(CAST(input_tokens  AS INTEGER)), 0)   AS total_input_tokens,
            COALESCE(SUM(CAST(output_tokens AS INTEGER)), 0)   AS total_output_tokens
        FROM audit_log
        GROUP BY provider, model
        ORDER BY total_calls DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def get_latency_stats(conn: sqlite3.Connection) -> dict[str, int | None]:
    """Return latency percentile statistics across all successful calls.

    Calculates p50, p95, min, and max from the ``latency_ms`` column for
    rows where ``status = 'success'`` and ``latency_ms IS NOT NULL``.

    Args:
        conn: Open sqlite3.Connection.

    Returns:
        Dict with keys ``p50``, ``p95``, ``min``, ``max``, and ``count``.
        All latency values are ``None`` when there are no qualifying rows.
    """
    cursor = conn.execute(
        "SELECT latency_ms FROM audit_log "
        "WHERE status = 'success' AND latency_ms IS NOT NULL "
        "ORDER BY latency_ms ASC"
    )
    values: list[int] = [row[0] for row in cursor.fetchall()]
    if not values:
        return {"p50": None, "p95": None, "min": None, "max": None, "count": 0}
    return {
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "min": values[0],
        "max": values[-1],
        "count": len(values),
    }


def get_provider_health(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return success rate and error details grouped by provider.

    Columns returned:
        - ``provider``: provider name
        - ``total_calls``: all calls for this provider
        - ``success_calls``: calls with status ``success``
        - ``error_calls``: calls with status ``error`` or ``flagged``
        - ``success_rate``: float 0.0–100.0 (0.0 when total_calls is 0)
        - ``last_error_time``: ISO timestamp of the most recent error/flagged call
        - ``last_error_message``: error_message from the most recent failure

    Args:
        conn: Open sqlite3.Connection.

    Returns:
        List of dicts ordered by total_calls descending.
    """
    cursor = conn.execute(
        """
        SELECT
            provider,
            COUNT(*)                                                AS total_calls,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END)    AS success_calls,
            SUM(CASE WHEN status IN ('error','flagged') THEN 1 ELSE 0 END)
                                                                    AS error_calls,
            MAX(CASE WHEN status IN ('error','flagged') THEN timestamp
                     ELSE NULL END)                                 AS last_error_time,
            MAX(CASE WHEN status IN ('error','flagged') THEN error_message
                     ELSE NULL END)                                 AS last_error_message
        FROM audit_log
        GROUP BY provider
        ORDER BY total_calls DESC
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    for row in rows:
        total = row["total_calls"] or 0
        row["success_rate"] = round(row["success_calls"] / total * 100, 1) if total else 0.0
    return rows


def get_session_activity(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return sessions ranked by call volume with timing and error info.

    Columns returned:
        - ``session_id``: session identifier
        - ``total_calls``: number of calls in the session
        - ``user_id``: user who made the calls (most-common value)
        - ``first_call``: ISO timestamp of the first call in the session
        - ``last_call``: ISO timestamp of the most recent call
        - ``error_calls``: number of error/flagged calls in the session

    Args:
        conn: Open sqlite3.Connection.

    Returns:
        List of dicts ordered by total_calls descending.
    """
    cursor = conn.execute(
        """
        SELECT
            session_id,
            COUNT(*)                                                    AS total_calls,
            MAX(user_id)                                                AS user_id,
            MIN(timestamp)                                              AS first_call,
            MAX(timestamp)                                              AS last_call,
            SUM(CASE WHEN status IN ('error','flagged') THEN 1 ELSE 0 END)
                                                                        AS error_calls
        FROM audit_log
        GROUP BY session_id
        ORDER BY total_calls DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]
