"""Shared pytest fixtures for all test modules."""

from __future__ import annotations

import sqlite3
from typing import Generator
from unittest.mock import MagicMock

import pytest

from src.audit.logger import AuditLogger
from src.config import Settings
from src.db.schema import ensure_schema
from src.models.log_entry import LogEntry, LogStatus


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield an in-memory sqlite3.Connection with the audit schema applied.

    Yields:
        Open sqlite3.Connection backed by :memory:.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def audit_logger(mem_conn: sqlite3.Connection) -> AuditLogger:
    """Return an AuditLogger wired to the in-memory test DB.

    Args:
        mem_conn: In-memory DB connection fixture.

    Returns:
        AuditLogger instance ready for testing.
    """
    return AuditLogger(mem_conn)


# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_settings() -> Settings:
    """Return a Settings instance with safe test defaults.

    Returns:
        Settings with non-empty stubs for all required fields.
    """
    return Settings(
        anthropic_api_key="test-ant-key",
        anthropic_model="claude-test",
        openai_api_key="test-oai-key",
        openai_model="gpt-test",
        llama_model_path="./models/test.gguf",
        llama_n_ctx=512,
        llama_n_gpu_layers=0,
        llama_n_threads=1,
        audit_store_path=":memory:",
        environment="local",
        log_level="DEBUG",
    )


# ---------------------------------------------------------------------------
# Sample LogEntry fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_entry() -> LogEntry:
    """Return a fully-populated LogEntry for use in tests.

    Returns:
        LogEntry with status=success.
    """
    return LogEntry(
        id="00000000-0000-0000-0000-000000000001",
        timestamp="2026-03-22T12:00:00+00:00",
        session_id="ses-test-001",
        user_id="user-test-001",
        provider="anthropic",
        model="claude-test",
        prompt="What is 2 + 2?",
        response="4",
        input_tokens=10,
        output_tokens=1,
        latency_ms=42,
        status=LogStatus.success,
        error_message=None,
    )


@pytest.fixture()
def error_entry() -> LogEntry:
    """Return a LogEntry with status=error.

    Returns:
        LogEntry representing a failed call.
    """
    return LogEntry(
        id="00000000-0000-0000-0000-000000000002",
        timestamp="2026-03-22T12:01:00+00:00",
        session_id="ses-test-001",
        user_id="user-test-001",
        provider="openai",
        model="gpt-test",
        prompt="Trigger an error.",
        response=None,
        input_tokens=None,
        output_tokens=None,
        latency_ms=5,
        status=LogStatus.error,
        error_message="RateLimitError: quota exceeded",
    )


# ---------------------------------------------------------------------------
# Mock provider clients
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_anthropic_response() -> MagicMock:
    """Return a MagicMock shaped like an Anthropic Message response.

    Returns:
        MagicMock with .content[0].text and .usage attributes.
    """
    resp = MagicMock()
    resp.content = [MagicMock(text="Mocked Anthropic response")]
    resp.usage = MagicMock(input_tokens=20, output_tokens=5)
    return resp


@pytest.fixture()
def mock_openai_response() -> MagicMock:
    """Return a MagicMock shaped like an OpenAI ChatCompletion response.

    Returns:
        MagicMock with .choices[0].message.content and .usage attributes.
    """
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="Mocked OpenAI response"))]
    resp.usage = MagicMock(prompt_tokens=15, completion_tokens=8)
    return resp


@pytest.fixture()
def mock_llama_response() -> dict[str, object]:
    """Return a dict shaped like a llama-cpp-python completion response.

    Returns:
        Dict with choices, usage, and id fields.
    """
    return {
        "id": "cmpl-test-001",
        "choices": [{"text": "Mocked llama response", "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }
