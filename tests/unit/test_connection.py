"""Unit tests for src/db/connection.py."""

from __future__ import annotations

import os
import sqlite3
import tempfile

from src.db.connection import get_connection


class TestGetConnection:
    """Tests for the get_connection context manager."""

    def test_memory_connection_yields_sqlite_conn(self) -> None:
        with get_connection(":memory:") as conn:
            assert isinstance(conn, sqlite3.Connection)

    def test_row_factory_is_sqlite_row(self) -> None:
        with get_connection(":memory:") as conn:
            assert conn.row_factory is sqlite3.Row

    def test_connection_is_closed_after_context(self) -> None:
        with get_connection(":memory:") as conn:
            pass
        # After close, executing should raise ProgrammingError
        try:
            conn.execute("SELECT 1")
            assert False, "Expected ProgrammingError"
        except Exception:
            pass  # expected — connection is closed

    def test_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "nested", "subdir", "test.db")
            with get_connection(db_path) as conn:
                assert isinstance(conn, sqlite3.Connection)
            assert os.path.exists(db_path)

    def test_file_based_db_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "persist.db")
            with get_connection(db_path) as conn:
                conn.execute("CREATE TABLE t (x INTEGER)")
                conn.execute("INSERT INTO t VALUES (42)")
                conn.commit()
            with get_connection(db_path) as conn:
                cursor = conn.execute("SELECT x FROM t")
                assert cursor.fetchone()[0] == 42

    def test_multiple_contexts_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "multi.db")
            with get_connection(db_path) as c1:
                c1.execute("CREATE TABLE t (x INTEGER)")
                c1.commit()
            with get_connection(db_path) as c2:
                c2.execute("INSERT INTO t VALUES (7)")
                c2.commit()
            with get_connection(db_path) as c3:
                cursor = c3.execute("SELECT x FROM t")
                assert cursor.fetchone()[0] == 7
