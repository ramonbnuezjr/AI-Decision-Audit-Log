"""Unit tests for all eight query functions in src/db/query.py."""

from __future__ import annotations

import sqlite3

import pytest

from src.db.query import (
    get_all_calls,
    get_by_session,
    get_by_user,
    get_errors,
    get_latency_stats,
    get_model_usage_summary,
    get_provider_health,
    get_session_activity,
)
from src.db.schema import INSERT_SQL
from src.models.log_entry import LogEntry, LogStatus


def _insert(conn: sqlite3.Connection, entry: LogEntry) -> None:
    conn.execute(INSERT_SQL, entry.to_sqlite_row())
    conn.commit()


def _make_entry(
    entry_id: str,
    *,
    session_id: str = "ses-1",
    user_id: str = "usr-1",
    provider: str = "anthropic",
    model: str = "claude-test",
    status: LogStatus = LogStatus.success,
    timestamp: str = "2026-01-01T00:00:00+00:00",
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    latency_ms: int = 50,
) -> LogEntry:
    return LogEntry(
        id=entry_id,
        timestamp=timestamp,
        session_id=session_id,
        user_id=user_id,
        provider=provider,
        model=model,
        prompt=f"prompt-{entry_id}",
        response=f"response-{entry_id}" if status == LogStatus.success else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        status=status,
        error_message="oops" if status == LogStatus.error else None,
    )


class TestGetAllCalls:
    def test_empty_db_returns_empty_list(self, mem_conn: sqlite3.Connection) -> None:
        assert get_all_calls(mem_conn) == []

    def test_returns_all_entries(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("a1"))
        _insert(mem_conn, _make_entry("a2"))
        _insert(mem_conn, _make_entry("a3"))
        results = get_all_calls(mem_conn)
        assert len(results) == 3

    def test_ordered_by_timestamp_desc(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("t1", timestamp="2026-01-01T10:00:00+00:00"))
        _insert(mem_conn, _make_entry("t2", timestamp="2026-01-01T12:00:00+00:00"))
        _insert(mem_conn, _make_entry("t3", timestamp="2026-01-01T11:00:00+00:00"))
        results = get_all_calls(mem_conn)
        timestamps = [r.timestamp for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_returns_log_entry_instances(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("le1"))
        results = get_all_calls(mem_conn)
        assert all(isinstance(r, LogEntry) for r in results)


class TestGetBySession:
    def test_filters_by_session(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("s1", session_id="ses-A"))
        _insert(mem_conn, _make_entry("s2", session_id="ses-B"))
        _insert(mem_conn, _make_entry("s3", session_id="ses-A"))
        results = get_by_session(mem_conn, "ses-A")
        assert len(results) == 2
        assert all(r.session_id == "ses-A" for r in results)

    def test_returns_empty_for_unknown_session(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("sx"))
        assert get_by_session(mem_conn, "ses-UNKNOWN") == []

    def test_ordered_ascending_for_conversation_replay(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert(mem_conn, _make_entry("c1", session_id="conv", timestamp="2026-01-01T10:00:00+00:00"))
        _insert(mem_conn, _make_entry("c2", session_id="conv", timestamp="2026-01-01T10:02:00+00:00"))
        _insert(mem_conn, _make_entry("c3", session_id="conv", timestamp="2026-01-01T10:01:00+00:00"))
        results = get_by_session(mem_conn, "conv")
        timestamps = [r.timestamp for r in results]
        assert timestamps == sorted(timestamps)


class TestGetByUser:
    def test_filters_by_user(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("u1", user_id="alice"))
        _insert(mem_conn, _make_entry("u2", user_id="bob"))
        _insert(mem_conn, _make_entry("u3", user_id="alice"))
        results = get_by_user(mem_conn, "alice")
        assert len(results) == 2
        assert all(r.user_id == "alice" for r in results)

    def test_returns_empty_for_unknown_user(self, mem_conn: sqlite3.Connection) -> None:
        assert get_by_user(mem_conn, "nobody") == []

    def test_ordered_desc(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ud1", user_id="alice", timestamp="2026-01-01T08:00:00+00:00"))
        _insert(mem_conn, _make_entry("ud2", user_id="alice", timestamp="2026-01-01T09:00:00+00:00"))
        results = get_by_user(mem_conn, "alice")
        assert results[0].timestamp > results[1].timestamp


class TestGetErrors:
    def test_returns_only_error_and_flagged(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ok1", status=LogStatus.success))
        _insert(mem_conn, _make_entry("er1", status=LogStatus.error))
        _insert(mem_conn, _make_entry("fl1", status=LogStatus.flagged))
        results = get_errors(mem_conn)
        assert len(results) == 2
        statuses = {r.status for r in results}
        assert statuses == {LogStatus.error, LogStatus.flagged}

    def test_returns_empty_when_no_errors(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ok2", status=LogStatus.success))
        assert get_errors(mem_conn) == []


class TestGetModelUsageSummary:
    def test_empty_db_returns_empty_list(self, mem_conn: sqlite3.Connection) -> None:
        assert get_model_usage_summary(mem_conn) == []

    def test_groups_by_provider_and_model(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("m1", provider="anthropic", model="claude-a"))
        _insert(mem_conn, _make_entry("m2", provider="anthropic", model="claude-a"))
        _insert(mem_conn, _make_entry("m3", provider="openai", model="gpt-4"))
        rows = get_model_usage_summary(mem_conn)
        providers = {r["provider"] for r in rows}
        assert "anthropic" in providers
        assert "openai" in providers

    def test_total_calls_is_accurate(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(5):
            _insert(mem_conn, _make_entry(f"tc{i}", provider="anthropic", model="m"))
        rows = get_model_usage_summary(mem_conn)
        ant_row = next(r for r in rows if r["provider"] == "anthropic")
        assert ant_row["total_calls"] == 5

    def test_successful_and_error_counts(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("sc1", status=LogStatus.success, provider="openai", model="g"))
        _insert(mem_conn, _make_entry("sc2", status=LogStatus.success, provider="openai", model="g"))
        _insert(mem_conn, _make_entry("sc3", status=LogStatus.error, provider="openai", model="g"))
        rows = get_model_usage_summary(mem_conn)
        row = rows[0]
        assert row["successful_calls"] == 2
        assert row["error_calls"] == 1

    def test_token_sums(self, mem_conn: sqlite3.Connection) -> None:
        _insert(
            mem_conn,
            _make_entry("tk1", provider="anthropic", model="m", input_tokens=100, output_tokens=50),
        )
        _insert(
            mem_conn,
            _make_entry("tk2", provider="anthropic", model="m", input_tokens=200, output_tokens=80),
        )
        rows = get_model_usage_summary(mem_conn)
        row = next(r for r in rows if r["provider"] == "anthropic")
        assert row["total_input_tokens"] == 300
        assert row["total_output_tokens"] == 130

    def test_null_tokens_treated_as_zero(self, mem_conn: sqlite3.Connection) -> None:
        _insert(
            mem_conn,
            _make_entry("nul1", provider="llama_cpp", model="gguf", input_tokens=None, output_tokens=None),
        )
        rows = get_model_usage_summary(mem_conn)
        row = next(r for r in rows if r["provider"] == "llama_cpp")
        assert row["total_input_tokens"] == 0
        assert row["total_output_tokens"] == 0

    def test_ordered_by_total_calls_desc(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("od1", provider="openai", model="g"))
        for i in range(3):
            _insert(mem_conn, _make_entry(f"oda{i}", provider="anthropic", model="m"))
        rows = get_model_usage_summary(mem_conn)
        counts = [r["total_calls"] for r in rows]
        assert counts == sorted(counts, reverse=True)


class TestGetLatencyStats:
    def test_empty_db_returns_none_values(self, mem_conn: sqlite3.Connection) -> None:
        result = get_latency_stats(mem_conn)
        assert result["count"] == 0
        assert result["p50"] is None
        assert result["p95"] is None
        assert result["min"] is None
        assert result["max"] is None

    def test_excludes_error_rows(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("e1", status=LogStatus.error, latency_ms=9999))
        result = get_latency_stats(mem_conn)
        assert result["count"] == 0

    def test_single_entry(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("s1", latency_ms=100))
        result = get_latency_stats(mem_conn)
        assert result["count"] == 1
        assert result["min"] == 100
        assert result["max"] == 100
        assert result["p50"] == 100
        assert result["p95"] == 100

    def test_min_max_accurate(self, mem_conn: sqlite3.Connection) -> None:
        for i, ms in enumerate([200, 50, 800, 300]):
            _insert(mem_conn, _make_entry(f"lat{i}", latency_ms=ms))
        result = get_latency_stats(mem_conn)
        assert result["min"] == 50
        assert result["max"] == 800

    def test_p50_is_median(self, mem_conn: sqlite3.Connection) -> None:
        for i, ms in enumerate([100, 200, 300, 400, 500]):
            _insert(mem_conn, _make_entry(f"p50e{i}", latency_ms=ms))
        result = get_latency_stats(mem_conn)
        assert result["p50"] is not None
        assert result["p50"] <= 300

    def test_p95_is_higher_than_p50(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(20):
            _insert(mem_conn, _make_entry(f"p95e{i}", latency_ms=(i + 1) * 100))
        result = get_latency_stats(mem_conn)
        assert result["p95"] is not None
        assert result["p50"] is not None
        assert result["p95"] >= result["p50"]

    def test_count_matches_successful_entries(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(3):
            _insert(mem_conn, _make_entry(f"ok{i}", latency_ms=100))
        _insert(mem_conn, _make_entry("err1", status=LogStatus.error, latency_ms=200))
        result = get_latency_stats(mem_conn)
        assert result["count"] == 3


class TestGetProviderHealth:
    def test_empty_db_returns_empty_list(self, mem_conn: sqlite3.Connection) -> None:
        assert get_provider_health(mem_conn) == []

    def test_returns_one_row_per_provider(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ph1", provider="anthropic"))
        _insert(mem_conn, _make_entry("ph2", provider="openai"))
        _insert(mem_conn, _make_entry("ph3", provider="anthropic"))
        rows = get_provider_health(mem_conn)
        providers = {r["provider"] for r in rows}
        assert providers == {"anthropic", "openai"}

    def test_success_rate_100_when_all_succeed(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(4):
            _insert(mem_conn, _make_entry(f"sr{i}", provider="openai", status=LogStatus.success))
        rows = get_provider_health(mem_conn)
        row = rows[0]
        assert row["success_rate"] == 100.0

    def test_success_rate_zero_when_all_fail(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(3):
            _insert(mem_conn, _make_entry(f"fail{i}", provider="anthropic", status=LogStatus.error))
        rows = get_provider_health(mem_conn)
        row = rows[0]
        assert row["success_rate"] == 0.0

    def test_success_rate_partial(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ok", provider="openai", status=LogStatus.success))
        _insert(mem_conn, _make_entry("bad", provider="openai", status=LogStatus.error))
        rows = get_provider_health(mem_conn)
        row = rows[0]
        assert row["success_rate"] == 50.0

    def test_error_calls_count(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ec1", provider="anthropic", status=LogStatus.error))
        _insert(mem_conn, _make_entry("ec2", provider="anthropic", status=LogStatus.flagged))
        _insert(mem_conn, _make_entry("ec3", provider="anthropic", status=LogStatus.success))
        rows = get_provider_health(mem_conn)
        row = rows[0]
        assert row["error_calls"] == 2

    def test_last_error_message_populated(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("em1", provider="openai", status=LogStatus.error))
        rows = get_provider_health(mem_conn)
        row = rows[0]
        assert row["last_error_message"] == "oops"

    def test_last_error_message_none_when_no_errors(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert(mem_conn, _make_entry("ok2", provider="anthropic", status=LogStatus.success))
        rows = get_provider_health(mem_conn)
        row = rows[0]
        assert row["last_error_message"] is None


class TestGetSessionActivity:
    def test_empty_db_returns_empty_list(self, mem_conn: sqlite3.Connection) -> None:
        assert get_session_activity(mem_conn) == []

    def test_returns_one_row_per_session(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("sa1", session_id="ses-A"))
        _insert(mem_conn, _make_entry("sa2", session_id="ses-B"))
        _insert(mem_conn, _make_entry("sa3", session_id="ses-A"))
        rows = get_session_activity(mem_conn)
        assert len(rows) == 2

    def test_total_calls_per_session(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(3):
            _insert(mem_conn, _make_entry(f"tc{i}", session_id="ses-X"))
        rows = get_session_activity(mem_conn)
        assert rows[0]["total_calls"] == 3

    def test_ordered_by_total_calls_desc(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("big1", session_id="big"))
        _insert(mem_conn, _make_entry("big2", session_id="big"))
        _insert(mem_conn, _make_entry("big3", session_id="big"))
        _insert(mem_conn, _make_entry("small1", session_id="small"))
        rows = get_session_activity(mem_conn)
        counts = [r["total_calls"] for r in rows]
        assert counts == sorted(counts, reverse=True)

    def test_error_calls_counted(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("good", session_id="ses-M", status=LogStatus.success))
        _insert(mem_conn, _make_entry("bad", session_id="ses-M", status=LogStatus.error))
        rows = get_session_activity(mem_conn)
        row = rows[0]
        assert row["error_calls"] == 1

    def test_first_and_last_call_timestamps(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("ts1", session_id="ses-T", timestamp="2026-01-01T08:00:00+00:00"))
        _insert(mem_conn, _make_entry("ts2", session_id="ses-T", timestamp="2026-01-01T10:00:00+00:00"))
        rows = get_session_activity(mem_conn)
        row = rows[0]
        assert row["first_call"] < row["last_call"]

    def test_user_id_captured(self, mem_conn: sqlite3.Connection) -> None:
        _insert(mem_conn, _make_entry("uid1", session_id="ses-U", user_id="ramon"))
        rows = get_session_activity(mem_conn)
        assert rows[0]["user_id"] == "ramon"
