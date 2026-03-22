"""Unit tests for AuditLogger — pre/post hooks, DB writes, error handling."""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.audit.logger import AuditLogger
from src.db.query import get_all_calls, get_errors
from src.models.log_entry import LogStatus


def _make_call_fn(return_value: Any) -> Any:
    """Return a mock callable that returns ``return_value``."""
    return MagicMock(return_value=return_value)


def _make_call_fn_raising(exc: Exception) -> Any:
    """Return a mock callable that raises ``exc``."""
    m = MagicMock(side_effect=exc)
    return m


class TestAuditLoggerSuccess:
    """Tests for successful call logging."""

    def test_returns_extracted_response(
        self, audit_logger: AuditLogger
    ) -> None:
        raw = MagicMock()
        result = audit_logger.log_call(
            session_id="s1",
            user_id="u1",
            provider="anthropic",
            model="m",
            prompt="hello",
            call_fn=_make_call_fn(raw),
            response_extractor=lambda _: "extracted text",
        )
        assert result == "extracted text"

    def test_writes_one_row_to_db(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        audit_logger.log_call(
            session_id="s1",
            user_id="u1",
            provider="openai",
            model="gpt-test",
            prompt="hi",
            call_fn=_make_call_fn(MagicMock()),
            response_extractor=lambda _: "ok",
        )
        entries = get_all_calls(mem_conn)
        assert len(entries) == 1

    def test_persisted_entry_has_correct_fields(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        audit_logger.log_call(
            session_id="ses-abc",
            user_id="usr-xyz",
            provider="anthropic",
            model="claude-v",
            prompt="test prompt",
            call_fn=_make_call_fn(MagicMock()),
            response_extractor=lambda _: "the response",
        )
        entries = get_all_calls(mem_conn)
        e = entries[0]
        assert e.session_id == "ses-abc"
        assert e.user_id == "usr-xyz"
        assert e.provider == "anthropic"
        assert e.model == "claude-v"
        assert e.prompt == "test prompt"
        assert e.response == "the response"
        assert e.status == LogStatus.success

    def test_token_extractor_is_stored(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        audit_logger.log_call(
            session_id="s",
            user_id="u",
            provider="anthropic",
            model="m",
            prompt="p",
            call_fn=_make_call_fn(MagicMock()),
            response_extractor=lambda _: "r",
            token_extractor=lambda _: (42, 7),
        )
        entry = get_all_calls(mem_conn)[0]
        assert entry.input_tokens == 42
        assert entry.output_tokens == 7

    def test_latency_is_positive_integer(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        audit_logger.log_call(
            session_id="s",
            user_id="u",
            provider="openai",
            model="m",
            prompt="p",
            call_fn=_make_call_fn(MagicMock()),
            response_extractor=lambda _: "r",
        )
        entry = get_all_calls(mem_conn)[0]
        assert entry.latency_ms is not None
        assert entry.latency_ms >= 0

    def test_entry_id_is_unique_uuid(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        for _ in range(3):
            audit_logger.log_call(
                session_id="s",
                user_id="u",
                provider="openai",
                model="m",
                prompt="p",
                call_fn=_make_call_fn(MagicMock()),
                response_extractor=lambda _: "r",
            )
        entries = get_all_calls(mem_conn)
        ids = [e.id for e in entries]
        assert len(set(ids)) == 3

    def test_kwargs_forwarded_to_call_fn(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from src.db.schema import ensure_schema

        ensure_schema(conn)
        logger = AuditLogger(conn)
        spy = MagicMock(return_value=MagicMock())
        logger.log_call(
            session_id="s",
            user_id="u",
            provider="openai",
            model="m",
            prompt="p",
            call_fn=spy,
            response_extractor=lambda _: "r",
            extra_kwarg="fwd",
        )
        spy.assert_called_once_with(extra_kwarg="fwd")
        conn.close()


class TestAuditLoggerError:
    """Tests for error recording and re-raise behaviour."""

    def test_reraises_exception(self, audit_logger: AuditLogger) -> None:
        with pytest.raises(ValueError, match="provider blew up"):
            audit_logger.log_call(
                session_id="s",
                user_id="u",
                provider="openai",
                model="m",
                prompt="p",
                call_fn=_make_call_fn_raising(ValueError("provider blew up")),
                response_extractor=lambda _: "",
            )

    def test_error_entry_written_to_db(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(RuntimeError):
            audit_logger.log_call(
                session_id="s",
                user_id="u",
                provider="anthropic",
                model="m",
                prompt="p",
                call_fn=_make_call_fn_raising(RuntimeError("network error")),
                response_extractor=lambda _: "",
            )
        errors = get_errors(mem_conn)
        assert len(errors) == 1
        assert errors[0].status == LogStatus.error
        assert "network error" in (errors[0].error_message or "")

    def test_error_entry_has_null_response(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(Exception):  # broad: intentional in test  # noqa: B017
            audit_logger.log_call(
                session_id="s",
                user_id="u",
                provider="openai",
                model="m",
                prompt="p",
                call_fn=_make_call_fn_raising(Exception("fail")),
                response_extractor=lambda _: "",
            )
        entry = get_errors(mem_conn)[0]
        assert entry.response is None

    def test_multiple_calls_mix_success_and_error(
        self, audit_logger: AuditLogger, mem_conn: sqlite3.Connection
    ) -> None:
        audit_logger.log_call(
            session_id="s",
            user_id="u",
            provider="anthropic",
            model="m",
            prompt="ok",
            call_fn=_make_call_fn(MagicMock()),
            response_extractor=lambda _: "ok",
        )
        with pytest.raises(Exception):  # noqa: B017
            audit_logger.log_call(
                session_id="s",
                user_id="u",
                provider="anthropic",
                model="m",
                prompt="fail",
                call_fn=_make_call_fn_raising(Exception("boom")),
                response_extractor=lambda _: "",
            )
        all_entries = get_all_calls(mem_conn)
        assert len(all_entries) == 2
        statuses = {e.status for e in all_entries}
        assert statuses == {LogStatus.success, LogStatus.error}
