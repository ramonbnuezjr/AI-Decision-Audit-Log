"""Unit tests for LogEntry Pydantic model and LogStatus enum."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.log_entry import LogEntry, LogStatus


class TestLogStatus:
    """Tests for the LogStatus enum."""

    def test_values_are_strings(self) -> None:
        assert LogStatus.success == "success"
        assert LogStatus.error == "error"
        assert LogStatus.flagged == "flagged"

    def test_all_three_variants_exist(self) -> None:
        variants = {s.value for s in LogStatus}
        assert variants == {"success", "error", "flagged"}


class TestLogEntryConstruction:
    """Tests for constructing valid LogEntry instances."""

    def test_minimal_valid_entry(self) -> None:
        entry = LogEntry(
            id="abc",
            timestamp="2026-01-01T00:00:00+00:00",
            session_id="ses-1",
            user_id="usr-1",
            provider="anthropic",
            model="claude-test",
            prompt="Hello",
            status=LogStatus.success,
        )
        assert entry.id == "abc"
        assert entry.response is None
        assert entry.input_tokens is None
        assert entry.output_tokens is None
        assert entry.latency_ms is None
        assert entry.error_message is None

    def test_full_success_entry(self, sample_entry: LogEntry) -> None:
        assert sample_entry.status == LogStatus.success
        assert sample_entry.response == "4"
        assert sample_entry.input_tokens == 10
        assert sample_entry.output_tokens == 1
        assert sample_entry.latency_ms == 42

    def test_error_entry(self, error_entry: LogEntry) -> None:
        assert error_entry.status == LogStatus.error
        assert error_entry.response is None
        assert error_entry.error_message == "RateLimitError: quota exceeded"

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            LogEntry(
                id="x",
                timestamp="2026-01-01T00:00:00+00:00",
                session_id="s",
                user_id="u",
                provider="anthropic",
                model="m",
                prompt="p",
                status="invalid_status",  # type: ignore[arg-type]
            )

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            LogEntry(  # type: ignore[call-arg]
                id="x",
                timestamp="2026-01-01T00:00:00+00:00",
                session_id="s",
                user_id="u",
                provider="anthropic",
                # model missing
                prompt="p",
                status=LogStatus.success,
            )


class TestLogEntrySerialization:
    """Tests for to_sqlite_row / from_sqlite_row round-trip."""

    def test_round_trip_success(self, sample_entry: LogEntry) -> None:
        row = sample_entry.to_sqlite_row()
        restored = LogEntry.from_sqlite_row(row)
        assert restored == sample_entry

    def test_round_trip_null_fields(self) -> None:
        entry = LogEntry(
            id="x",
            timestamp="2026-01-01T00:00:00+00:00",
            session_id="s",
            user_id="u",
            provider="llama_cpp",
            model="./models/test.gguf",
            prompt="hi",
            status=LogStatus.success,
        )
        row = entry.to_sqlite_row()
        assert row[8] is None  # input_tokens
        assert row[9] is None  # output_tokens
        assert row[10] is None  # latency_ms
        restored = LogEntry.from_sqlite_row(row)
        assert restored.input_tokens is None
        assert restored.output_tokens is None

    def test_round_trip_error_entry(self, error_entry: LogEntry) -> None:
        row = error_entry.to_sqlite_row()
        restored = LogEntry.from_sqlite_row(row)
        assert restored.status == LogStatus.error
        assert restored.error_message == error_entry.error_message

    def test_sqlite_row_length(self, sample_entry: LogEntry) -> None:
        assert len(sample_entry.to_sqlite_row()) == 13

    def test_status_serialised_as_value(self, sample_entry: LogEntry) -> None:
        row = sample_entry.to_sqlite_row()
        assert row[11] == "success"
