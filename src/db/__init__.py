"""SQLite database layer — schema, connection management, and query utilities."""

from src.db.connection import get_connection
from src.db.schema import ensure_schema

__all__ = ["ensure_schema", "get_connection"]
