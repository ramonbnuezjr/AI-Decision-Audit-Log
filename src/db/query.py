"""Query utilities for the audit_log SQLite table."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.models.log_entry import LogEntry


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
