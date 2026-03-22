"""AuditLogger — provider-agnostic middleware that intercepts every LLM call.

Usage::

    with get_connection(settings.audit_store_path) as conn:
        ensure_schema(conn)
        logger = AuditLogger(conn)
        response_text = logger.log_call(
            session_id="ses-123",
            user_id="user-456",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            prompt="Summarise this document...",
            call_fn=client.messages.create,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Summarise this document..."}],
            max_tokens=1024,
        )
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

from src.db.schema import INSERT_SQL
from src.models.log_entry import LogEntry, LogStatus

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Intercepts LLM API calls and writes a structured LogEntry to SQLite.

    The logger is provider-agnostic: it accepts any callable as ``call_fn``
    and delegates token/response extraction to provider-specific extractors
    injected at construction time.  This keeps the logger decoupled from every
    SDK's response shape.

    Args:
        conn: Open sqlite3.Connection with the audit_log schema applied.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_call(
        self,
        *,
        session_id: str,
        user_id: str,
        provider: str,
        model: str,
        prompt: str,
        call_fn: Callable[..., Any],
        response_extractor: Callable[[Any], str],
        token_extractor: Callable[[Any], tuple[int | None, int | None]] | None = None,
        **call_kwargs: Any,
    ) -> str:
        """Execute ``call_fn`` and write a complete audit record to SQLite.

        The method is synchronous — the call blocks until the provider returns.
        It is a transparent passthrough: the return value is the raw response
        text extracted by ``response_extractor``, identical to what the caller
        would have received if they called the SDK directly.

        Args:
            session_id: Conversation session identifier.
            user_id: Caller-supplied user identifier.
            provider: Provider name (``anthropic``, ``openai``, ``llama_cpp``).
            model: Exact model version string.
            prompt: Full prompt text sent to the model.
            call_fn: The SDK function to call (e.g. ``client.messages.create``).
            response_extractor: Callable that receives the raw SDK response and
                returns the completion text as a ``str``.
            token_extractor: Optional callable that receives the raw SDK response
                and returns ``(input_tokens, output_tokens)`` as ints or None.
            **call_kwargs: All keyword arguments forwarded verbatim to
                ``call_fn``.

        Returns:
            The completion text returned by the model.

        Raises:
            Re-raises any exception from ``call_fn`` after writing an error
            record to the audit log.
        """
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        start_ns = time.perf_counter_ns()

        logger.debug(
            "audit.call.start",
            entry_id=entry_id,
            provider=provider,
            model=model,
            session_id=session_id,
            user_id=user_id,
        )

        raw_response: Any = None
        status = LogStatus.success
        error_message: str | None = None

        try:
            raw_response = call_fn(**call_kwargs)
        except Exception as exc:  # broad catch: all provider errors must be logged
            status = LogStatus.error
            error_message = str(exc)
            logger.error(
                "audit.call.error",
                entry_id=entry_id,
                provider=provider,
                model=model,
                error=error_message,
            )
            self._write(
                entry_id=entry_id,
                timestamp=timestamp,
                session_id=session_id,
                user_id=user_id,
                provider=provider,
                model=model,
                prompt=prompt,
                response=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=self._elapsed_ms(start_ns),
                status=status,
                error_message=error_message,
            )
            raise

        latency_ms = self._elapsed_ms(start_ns)
        response_text = response_extractor(raw_response)
        input_tokens: int | None = None
        output_tokens: int | None = None
        if token_extractor is not None:
            input_tokens, output_tokens = token_extractor(raw_response)

        self._write(
            entry_id=entry_id,
            timestamp=timestamp,
            session_id=session_id,
            user_id=user_id,
            provider=provider,
            model=model,
            prompt=prompt,
            response=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=None,
        )

        logger.debug(
            "audit.call.success",
            entry_id=entry_id,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return response_text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _elapsed_ms(start_ns: int) -> int:
        """Compute elapsed milliseconds since ``start_ns`` (perf_counter_ns).

        Args:
            start_ns: Start timestamp from ``time.perf_counter_ns()``.

        Returns:
            Elapsed time in whole milliseconds.
        """
        return (time.perf_counter_ns() - start_ns) // 1_000_000

    def _write(
        self,
        *,
        entry_id: str,
        timestamp: str,
        session_id: str,
        user_id: str,
        provider: str,
        model: str,
        prompt: str,
        response: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int,
        status: LogStatus,
        error_message: str | None,
    ) -> None:
        """Build, validate, and persist a LogEntry to SQLite.

        Args:
            entry_id: UUID string for this record.
            timestamp: ISO 8601 UTC string.
            session_id: Session identifier.
            user_id: User identifier.
            provider: Provider name.
            model: Model version string.
            prompt: Input text.
            response: Output text or None on error.
            input_tokens: Prompt token count or None.
            output_tokens: Completion token count or None.
            latency_ms: Elapsed milliseconds.
            status: LogStatus enum value.
            error_message: Exception string or None.
        """
        entry = LogEntry(
            id=entry_id,
            timestamp=timestamp,
            session_id=session_id,
            user_id=user_id,
            provider=provider,
            model=model,
            prompt=prompt,
            response=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        )
        self._conn.execute(INSERT_SQL, entry.to_sqlite_row())
        self._conn.commit()
