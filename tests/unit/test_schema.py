"""Unit tests for src/db/schema.py — DDL and ensure_schema."""

from __future__ import annotations

import sqlite3

import pytest

from src.db.schema import DDL, INSERT_SQL, ensure_schema
from src.models.log_entry import LogEntry, LogStatus


@pytest.fixture()
def raw_conn() -> sqlite3.Connection:
    """Return a bare in-memory connection with no schema applied."""
    return sqlite3.connect(":memory:")


class TestEnsureSchema:
    """Tests for the ensure_schema() function."""

    def test_creates_audit_log_table(self, raw_conn: sqlite3.Connection) -> None:
        ensure_schema(raw_conn)
        cursor = raw_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
        )
        assert cursor.fetchone() is not None

    def test_idempotent_second_call(self, raw_conn: sqlite3.Connection) -> None:
        ensure_schema(raw_conn)
        ensure_schema(raw_conn)  # must not raise
        cursor = raw_conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        count = cursor.fetchone()[0]
        assert count == 1

    def test_creates_all_five_indexes(self, raw_conn: sqlite3.Connection) -> None:
        ensure_schema(raw_conn)
        cursor = raw_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='audit_log'"
        )
        index_names = {row[0] for row in cursor.fetchall()}
        expected = {
            "idx_audit_session",
            "idx_audit_user",
            "idx_audit_provider",
            "idx_audit_status",
            "idx_audit_timestamp",
        }
        assert expected.issubset(index_names)

    def test_table_has_correct_columns(self, raw_conn: sqlite3.Connection) -> None:
        ensure_schema(raw_conn)
        cursor = raw_conn.execute("PRAGMA table_info(audit_log)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "timestamp",
            "session_id",
            "user_id",
            "provider",
            "model",
            "prompt",
            "response",
            "input_tokens",
            "output_tokens",
            "latency_ms",
            "status",
            "error_message",
        }
        assert columns == expected


class TestInsertSQL:
    """Tests that INSERT_SQL works correctly with LogEntry rows."""

    def test_insert_and_select(self, mem_conn: sqlite3.Connection) -> None:
        entry = LogEntry(
            id="ins-001",
            timestamp="2026-01-01T00:00:00+00:00",
            session_id="s1",
            user_id="u1",
            provider="anthropic",
            model="claude-test",
            prompt="test prompt",
            response="test response",
            input_tokens=5,
            output_tokens=3,
            latency_ms=10,
            status=LogStatus.success,
        )
        mem_conn.execute(INSERT_SQL, entry.to_sqlite_row())
        mem_conn.commit()
        cursor = mem_conn.execute("SELECT COUNT(*) FROM audit_log WHERE id = 'ins-001'")
        assert cursor.fetchone()[0] == 1

    def test_insert_null_fields(self, mem_conn: sqlite3.Connection) -> None:
        entry = LogEntry(
            id="ins-002",
            timestamp="2026-01-01T00:00:00+00:00",
            session_id="s1",
            user_id="u1",
            provider="llama_cpp",
            model="./test.gguf",
            prompt="hi",
            status=LogStatus.error,
            error_message="boom",
        )
        mem_conn.execute(INSERT_SQL, entry.to_sqlite_row())
        mem_conn.commit()
        cursor = mem_conn.execute(
            "SELECT input_tokens, response FROM audit_log WHERE id = 'ins-002'"
        )
        row = cursor.fetchone()
        assert row[0] is None
        assert row[1] is None
