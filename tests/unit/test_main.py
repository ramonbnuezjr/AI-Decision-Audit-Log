"""Unit tests for src/main.py — CLI argument parsing and command handlers."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings
from src.db.schema import INSERT_SQL, ensure_schema
from src.main import (
    _configure_logging,
    _entries_to_dicts,
    build_parser,
    cmd_capture,
    cmd_export,
    cmd_query,
    cmd_summary,
    main,
)
from src.models.log_entry import LogEntry, LogStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: object) -> Settings:
    defaults = dict(
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-oai-test",
        audit_store_path=":memory:",
        environment="local",
        log_level="DEBUG",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _make_args(**kwargs: object) -> MagicMock:
    """Build a MagicMock namespace with sensible defaults."""
    defaults = dict(
        prompt="hello",
        provider="anthropic",
        session_id=None,
        user_id="cli-user",
        max_tokens=64,
        session_id_arg=None,
        errors_only=False,
        format="json",
        output=None,
    )
    defaults.update(kwargs)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _seeded_db() -> sqlite3.Connection:
    """Return an in-memory DB with one success and one error entry."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    for entry in [
        LogEntry(
            id="main-s1",
            timestamp="2026-03-22T10:00:00+00:00",
            session_id="ses-main",
            user_id="usr-main",
            provider="anthropic",
            model="claude-test",
            prompt="p1",
            response="r1",
            input_tokens=10,
            output_tokens=5,
            latency_ms=20,
            status=LogStatus.success,
        ),
        LogEntry(
            id="main-e1",
            timestamp="2026-03-22T10:01:00+00:00",
            session_id="ses-main",
            user_id="usr-main",
            provider="openai",
            model="gpt-test",
            prompt="p2",
            response=None,
            input_tokens=None,
            output_tokens=None,
            latency_ms=5,
            status=LogStatus.error,
            error_message="timeout",
        ),
    ]:
        conn.execute(INSERT_SQL, entry.to_sqlite_row())
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_returns_argument_parser(self) -> None:
        import argparse

        assert isinstance(build_parser(), argparse.ArgumentParser)

    def test_capture_subcommand_exists(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["capture", "--prompt", "hi"])
        assert args.command == "capture"
        assert args.prompt == "hi"

    def test_query_subcommand_defaults(self) -> None:
        args = build_parser().parse_args(["query"])
        assert args.command == "query"
        assert args.session_id is None
        assert args.user_id is None
        assert args.errors_only is False

    def test_export_defaults(self) -> None:
        args = build_parser().parse_args(["export"])
        assert args.command == "export"
        assert args.format == "json"
        assert args.output is None

    def test_summary_subcommand(self) -> None:
        args = build_parser().parse_args(["summary"])
        assert args.command == "summary"

    def test_capture_provider_choices(self) -> None:
        for provider in ("anthropic", "openai", "llama_cpp"):
            args = build_parser().parse_args(
                ["capture", "--prompt", "x", "--provider", provider]
            )
            assert args.provider == provider

    def test_invalid_provider_exits(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["capture", "--prompt", "x", "--provider", "groq"])

    def test_query_mutual_exclusion(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["query", "--session-id", "s", "--user-id", "u"])


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def test_does_not_raise(self) -> None:
        _configure_logging("INFO")
        _configure_logging("DEBUG")
        _configure_logging("WARNING")

    def test_unknown_level_falls_back(self) -> None:
        _configure_logging("UNKNOWN")  # should not raise


# ---------------------------------------------------------------------------
# _entries_to_dicts
# ---------------------------------------------------------------------------


class TestEntriesToDicts:
    def test_empty_list(self) -> None:
        assert _entries_to_dicts([]) == []

    def test_converts_to_dicts(self, sample_entry: LogEntry) -> None:
        result = _entries_to_dicts([sample_entry])
        assert isinstance(result, list)
        assert isinstance(result[0], dict)
        assert result[0]["id"] == sample_entry.id

    def test_status_is_string(self, sample_entry: LogEntry) -> None:
        result = _entries_to_dicts([sample_entry])
        assert isinstance(result[0]["status"], str)


# ---------------------------------------------------------------------------
# cmd_query
# ---------------------------------------------------------------------------


class TestCmdQuery:
    def test_query_all_empty_db(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["query"])
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_conn_ctx,
        ):
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_query(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "No entries found" in captured.out
        conn.close()

    def test_query_all_shows_entries(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["query"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_query(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "anthropic" in captured.out or "openai" in captured.out
        conn.close()

    def test_query_by_session(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["query", "--session-id", "ses-main"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_query(args)
        assert result == 0
        conn.close()

    def test_query_by_user(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["query", "--user-id", "usr-main"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_query(args)
        assert result == 0
        conn.close()

    def test_query_errors_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["query", "--errors-only"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_query(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "timeout" in captured.out
        conn.close()

    def test_query_shows_error_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["query", "--errors-only"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            cmd_query(args)
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        conn.close()


# ---------------------------------------------------------------------------
# cmd_export
# ---------------------------------------------------------------------------


class TestCmdExport:
    def test_export_json_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["export"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_export(args)
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        conn.close()

    def test_export_json_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        args = build_parser().parse_args(["export", "--output", out_path])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_export(args)
        assert result == 0
        with open(out_path) as fh:
            data = json.load(fh)
        assert len(data) == 2
        conn.close()

    def test_unsupported_format_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["export"])
        args.format = "csv"
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_export(args)
        assert result == 1
        conn.close()


# ---------------------------------------------------------------------------
# cmd_summary
# ---------------------------------------------------------------------------


class TestCmdSummary:
    def test_empty_db_prints_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["summary"])
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_summary(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "No entries" in captured.out
        conn.close()

    def test_summary_shows_table(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(["summary"])
        conn = _seeded_db()
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_summary(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "PROVIDER" in captured.out
        assert "anthropic" in captured.out
        conn.close()


# ---------------------------------------------------------------------------
# cmd_capture
# ---------------------------------------------------------------------------


class TestCmdCapture:
    def test_capture_anthropic_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(
            ["capture", "--prompt", "hello", "--provider", "anthropic"]
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=3)

        mock_ant_instance = MagicMock()
        mock_ant_instance.messages.create.return_value = mock_response

        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
            patch("anthropic.Anthropic", return_value=mock_ant_instance),
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_capture(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Test response" in captured.out
        conn.close()

    def test_capture_openai_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_parser().parse_args(
            ["capture", "--prompt", "hello", "--provider", "openai"]
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OpenAI response"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3)

        mock_oai_instance = MagicMock()
        mock_oai_instance.chat.completions.create.return_value = mock_response

        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
            patch("openai.OpenAI", return_value=mock_oai_instance),
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_capture(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "OpenAI response" in captured.out
        conn.close()

    def test_capture_missing_anthropic_key_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(
            ["capture", "--prompt", "hi", "--provider", "anthropic"]
        )
        settings = _make_settings(anthropic_api_key="")
        with patch("src.main.get_settings", return_value=settings):
            result = cmd_capture(args)
        assert result == 1

    def test_capture_missing_openai_key_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(
            ["capture", "--prompt", "hi", "--provider", "openai"]
        )
        settings = _make_settings(openai_api_key="")
        with patch("src.main.get_settings", return_value=settings):
            result = cmd_capture(args)
        assert result == 1

    def test_capture_provider_exception_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(
            ["capture", "--prompt", "hi", "--provider", "anthropic"]
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        mock_ant_instance = MagicMock()
        mock_ant_instance.messages.create.side_effect = ConnectionError("timeout")

        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
            patch("anthropic.Anthropic", return_value=mock_ant_instance),
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_capture(args)

        assert result == 1
        conn.close()

    def test_capture_llama_cpp_uses_no_api_key(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(
            ["capture", "--prompt", "local prompt", "--provider", "llama_cpp"]
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        mock_llama = MagicMock(
            return_value={"choices": [{"text": "local response"}], "usage": {}}
        )

        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
            patch("src.agent.agent.Agent._get_or_load_llama", return_value=mock_llama),
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = cmd_capture(args)

        assert result == 0
        conn.close()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_summary_exits_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)
        with (
            patch("src.main.get_settings", return_value=_make_settings()),
            patch("src.main.get_connection") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            code = main(["summary"])
        assert code == 0
        conn.close()

    def test_main_no_command_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0
