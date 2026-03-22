"""sqlite3 connection management — context manager with row_factory pre-set."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator


@contextmanager
def get_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Yield an open sqlite3.Connection, closing it on exit.

    Creates the parent directory if it does not exist so callers never need
    to pre-create the data/ folder.

    Args:
        db_path: File path to the SQLite database, or ``:memory:`` for tests.

    Yields:
        An open sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
