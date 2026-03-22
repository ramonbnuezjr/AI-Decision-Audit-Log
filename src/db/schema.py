"""SQLite DDL and schema migration for the audit_log table."""

from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id            TEXT PRIMARY KEY,
    timestamp     TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    response      TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    status        TEXT NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_session   ON audit_log (session_id);
CREATE INDEX IF NOT EXISTS idx_audit_user      ON audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_provider  ON audit_log (provider, model);
CREATE INDEX IF NOT EXISTS idx_audit_status    ON audit_log (status);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log (timestamp);
"""

INSERT_SQL = """
INSERT INTO audit_log (
    id, timestamp, session_id, user_id, provider, model,
    prompt, response, input_tokens, output_tokens, latency_ms,
    status, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the audit_log table and indexes if they do not already exist.

    Idempotent — safe to call on every startup.

    Args:
        conn: An open sqlite3.Connection to the target database.
    """
    conn.executescript(DDL)
    conn.commit()
