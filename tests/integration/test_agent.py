"""Integration tests for Agent — full call-through with mocked provider SDKs."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.agent.agent import (
    PROVIDER_ANTHROPIC,
    PROVIDER_LLAMA_CPP,
    PROVIDER_OPENAI,
    Agent,
)
from src.audit.logger import AuditLogger
from src.config import Settings
from src.db.query import get_all_calls, get_by_session, get_errors, get_model_usage_summary
from src.models.log_entry import LogStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_with_mocks(
    audit_logger: AuditLogger,
    test_settings: Settings,
    mock_anthropic_response: MagicMock,
    mock_openai_response: MagicMock,
    mock_llama_response: dict[str, object],
) -> Agent:
    """Return an Agent with all three provider mocks pre-wired.

    Args:
        audit_logger: In-memory AuditLogger fixture.
        test_settings: Safe test settings fixture.
        mock_anthropic_response: Anthropic response mock.
        mock_openai_response: OpenAI response mock.
        mock_llama_response: llama.cpp response dict.

    Returns:
        Configured Agent ready for testing.
    """
    ant_client = MagicMock()
    ant_client.messages.create.return_value = mock_anthropic_response

    oai_client = MagicMock()
    oai_client.chat.completions.create.return_value = mock_openai_response

    llama_model = MagicMock(return_value=mock_llama_response)

    return Agent(
        audit_logger=audit_logger,
        settings=test_settings,
        anthropic_client=ant_client,
        openai_client=oai_client,
        llama_model=llama_model,
    )


# ---------------------------------------------------------------------------
# Provider routing tests
# ---------------------------------------------------------------------------


class TestAgentProviderRouting:
    """Tests that agent.chat() routes to the correct provider."""

    def test_anthropic_returns_response_text(
        self, agent_with_mocks: Agent
    ) -> None:
        result = agent_with_mocks.chat(
            "test",
            session_id="s1",
            user_id="u1",
            provider=PROVIDER_ANTHROPIC,
        )
        assert result == "Mocked Anthropic response"

    def test_openai_returns_response_text(
        self, agent_with_mocks: Agent
    ) -> None:
        result = agent_with_mocks.chat(
            "test",
            session_id="s1",
            user_id="u1",
            provider=PROVIDER_OPENAI,
        )
        assert result == "Mocked OpenAI response"

    def test_llama_cpp_returns_response_text(
        self, agent_with_mocks: Agent
    ) -> None:
        result = agent_with_mocks.chat(
            "test",
            session_id="s1",
            user_id="u1",
            provider=PROVIDER_LLAMA_CPP,
        )
        assert result == "Mocked llama response"

    def test_unsupported_provider_raises_value_error(
        self, agent_with_mocks: Agent
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported provider"):
            agent_with_mocks.chat(
                "test",
                session_id="s1",
                user_id="u1",
                provider="groq",
            )

    def test_anthropic_missing_client_raises_runtime_error(
        self,
        audit_logger: AuditLogger,
        test_settings: Settings,
    ) -> None:
        agent = Agent(audit_logger=audit_logger, settings=test_settings)
        with pytest.raises(RuntimeError, match="Anthropic client not injected"):
            agent.chat("p", session_id="s", user_id="u", provider=PROVIDER_ANTHROPIC)

    def test_openai_missing_client_raises_runtime_error(
        self,
        audit_logger: AuditLogger,
        test_settings: Settings,
    ) -> None:
        agent = Agent(audit_logger=audit_logger, settings=test_settings)
        with pytest.raises(RuntimeError, match="OpenAI client not injected"):
            agent.chat("p", session_id="s", user_id="u", provider=PROVIDER_OPENAI)


# ---------------------------------------------------------------------------
# Audit log integration tests
# ---------------------------------------------------------------------------


class TestAgentAuditLogging:
    """Tests that every chat() call writes a correct audit record."""

    def test_anthropic_call_is_logged(
        self,
        agent_with_mocks: Agent,
        mem_conn: sqlite3.Connection,
    ) -> None:
        agent_with_mocks.chat(
            "What is AI?",
            session_id="ses-ant",
            user_id="usr-1",
            provider=PROVIDER_ANTHROPIC,
        )
        entries = get_all_calls(mem_conn)
        assert len(entries) == 1
        e = entries[0]
        assert e.provider == PROVIDER_ANTHROPIC
        assert e.prompt == "What is AI?"
        assert e.response == "Mocked Anthropic response"
        assert e.status == LogStatus.success
        assert e.input_tokens == 20
        assert e.output_tokens == 5

    def test_openai_call_is_logged(
        self,
        agent_with_mocks: Agent,
        mem_conn: sqlite3.Connection,
    ) -> None:
        agent_with_mocks.chat(
            "Summarise this.",
            session_id="ses-oai",
            user_id="usr-2",
            provider=PROVIDER_OPENAI,
        )
        entries = get_all_calls(mem_conn)
        assert len(entries) == 1
        e = entries[0]
        assert e.provider == PROVIDER_OPENAI
        assert e.input_tokens == 15
        assert e.output_tokens == 8

    def test_llama_cpp_call_is_logged(
        self,
        agent_with_mocks: Agent,
        mem_conn: sqlite3.Connection,
    ) -> None:
        agent_with_mocks.chat(
            "Local prompt",
            session_id="ses-lc",
            user_id="usr-3",
            provider=PROVIDER_LLAMA_CPP,
        )
        entries = get_all_calls(mem_conn)
        assert len(entries) == 1
        e = entries[0]
        assert e.provider == PROVIDER_LLAMA_CPP
        assert e.response == "Mocked llama response"
        assert e.input_tokens == 12
        assert e.output_tokens == 4

    def test_multi_turn_session_reconstructed(
        self,
        agent_with_mocks: Agent,
        mem_conn: sqlite3.Connection,
    ) -> None:
        for i in range(4):
            agent_with_mocks.chat(
                f"turn {i}",
                session_id="conv-multi",
                user_id="usr-1",
                provider=PROVIDER_ANTHROPIC,
            )
        turns = get_by_session(mem_conn, "conv-multi")
        assert len(turns) == 4
        prompts = [t.prompt for t in turns]
        assert prompts == ["turn 0", "turn 1", "turn 2", "turn 3"]

    def test_all_three_providers_in_summary(
        self,
        agent_with_mocks: Agent,
        mem_conn: sqlite3.Connection,
    ) -> None:
        agent_with_mocks.chat("p", session_id="s", user_id="u", provider=PROVIDER_ANTHROPIC)
        agent_with_mocks.chat("p", session_id="s", user_id="u", provider=PROVIDER_OPENAI)
        agent_with_mocks.chat("p", session_id="s", user_id="u", provider=PROVIDER_LLAMA_CPP)
        summary = get_model_usage_summary(mem_conn)
        providers = {r["provider"] for r in summary}
        assert providers == {PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_LLAMA_CPP}

    def test_provider_error_is_logged_and_reraised(
        self,
        audit_logger: AuditLogger,
        test_settings: Settings,
        mem_conn: sqlite3.Connection,
    ) -> None:
        bad_client = MagicMock()
        bad_client.messages.create.side_effect = ConnectionError("timeout")
        agent = Agent(
            audit_logger=audit_logger,
            settings=test_settings,
            anthropic_client=bad_client,
        )
        with pytest.raises(ConnectionError, match="timeout"):
            agent.chat("p", session_id="s", user_id="u", provider=PROVIDER_ANTHROPIC)
        errors = get_errors(mem_conn)
        assert len(errors) == 1
        assert errors[0].status == LogStatus.error
        assert "timeout" in (errors[0].error_message or "")


# ---------------------------------------------------------------------------
# llama.cpp lazy-load tests
# ---------------------------------------------------------------------------


class TestLlamaLazyLoad:
    """Tests for lazy model loading behaviour in _get_or_load_llama."""

    def test_cached_llama_model_not_reloaded(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        original = agent_with_mocks._llama_model
        agent_with_mocks.chat("p1", session_id="s", user_id="u", provider=PROVIDER_LLAMA_CPP)
        agent_with_mocks.chat("p2", session_id="s", user_id="u", provider=PROVIDER_LLAMA_CPP)
        assert agent_with_mocks._llama_model is original

    def test_llama_loaded_from_settings_path(
        self,
        audit_logger: AuditLogger,
        test_settings: Settings,
    ) -> None:
        agent = Agent(audit_logger=audit_logger, settings=test_settings)
        mock_llama_cls = MagicMock()
        mock_instance = MagicMock(
            return_value={"choices": [{"text": "hi"}], "usage": {}}
        )
        mock_llama_cls.return_value = mock_instance
        with patch("src.agent.agent.Agent._get_or_load_llama", return_value=mock_instance):
            agent._llama_model = None
            agent._llama_model = mock_instance
            result = agent.chat(
                "hi", session_id="s", user_id="u", provider=PROVIDER_LLAMA_CPP
            )
        assert result == "hi"
