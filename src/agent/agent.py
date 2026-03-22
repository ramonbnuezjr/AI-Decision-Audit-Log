"""Monolithic agent that routes calls to Anthropic, OpenAI, or llama.cpp.

Every call goes through ``AuditLogger.log_call`` — no direct SDK calls are
made outside this module.  Provider clients are injected at construction time
so the agent remains fully testable without live API keys.

llama.cpp provider note:
    The ``Llama`` model object is loaded lazily on first use to avoid the
    startup cost when the llama_cpp provider is not needed in a session.
    On Apple Silicon M2/M2 Pro (8 GB), use ``n_gpu_layers=-1`` (all layers
    offloaded to Metal) for best throughput; set ``n_batch`` and ``n_ctx``
    according to your available unified memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.audit.logger import AuditLogger
from src.config import Settings

if TYPE_CHECKING:
    import anthropic
    import openai
    from llama_cpp import Llama

log = structlog.get_logger(__name__)

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_LLAMA_CPP = "llama_cpp"

SUPPORTED_PROVIDERS = {PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_LLAMA_CPP}


class Agent:
    """Routes LLM calls to the configured provider through AuditLogger.

    All three providers share the same calling convention:
    ``agent.chat(prompt, session_id=..., user_id=...)`` — the provider is
    selected by the ``provider`` argument or falls back to ``anthropic``.

    Args:
        audit_logger: AuditLogger instance wired to an open DB connection.
        settings: Application settings (models, paths, token counts).
        anthropic_client: Optional pre-built ``anthropic.Anthropic`` client.
        openai_client: Optional pre-built ``openai.OpenAI`` client.
        llama_model: Optional pre-loaded ``llama_cpp.Llama`` instance.
    """

    def __init__(
        self,
        audit_logger: AuditLogger,
        settings: Settings,
        anthropic_client: "anthropic.Anthropic | None" = None,
        openai_client: "openai.OpenAI | None" = None,
        llama_model: "Llama | None" = None,
    ) -> None:
        self._logger = audit_logger
        self._settings = settings
        self._anthropic_client = anthropic_client
        self._openai_client = openai_client
        self._llama_model = llama_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        prompt: str,
        *,
        session_id: str,
        user_id: str,
        provider: str = PROVIDER_ANTHROPIC,
        max_tokens: int = 1024,
    ) -> str:
        """Send a prompt to the selected provider and return the response text.

        The call is transparently logged — callers receive the same string
        they would get from a direct SDK call.

        Args:
            prompt: The full user prompt text.
            session_id: Conversation session identifier for audit grouping.
            user_id: Caller-supplied user identifier.
            provider: Target provider — ``anthropic``, ``openai``, or
                ``llama_cpp``.  Defaults to ``anthropic``.
            max_tokens: Maximum tokens in the completion.

        Returns:
            The model's response as a plain string.

        Raises:
            ValueError: If ``provider`` is not a supported value.
            RuntimeError: If the required client/model has not been injected.
        """
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider {provider!r}. "
                f"Choose from: {sorted(SUPPORTED_PROVIDERS)}"
            )

        log.debug("agent.chat", provider=provider, session_id=session_id)

        if provider == PROVIDER_ANTHROPIC:
            return self._chat_anthropic(
                prompt=prompt,
                session_id=session_id,
                user_id=user_id,
                max_tokens=max_tokens,
            )
        if provider == PROVIDER_OPENAI:
            return self._chat_openai(
                prompt=prompt,
                session_id=session_id,
                user_id=user_id,
                max_tokens=max_tokens,
            )
        return self._chat_llama_cpp(
            prompt=prompt,
            session_id=session_id,
            user_id=user_id,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Private provider methods
    # ------------------------------------------------------------------

    def _chat_anthropic(
        self,
        *,
        prompt: str,
        session_id: str,
        user_id: str,
        max_tokens: int,
    ) -> str:
        """Route a call through the Anthropic Messages API via AuditLogger.

        Args:
            prompt: User prompt text.
            session_id: Session identifier.
            user_id: User identifier.
            max_tokens: Max completion tokens.

        Returns:
            Model response text.

        Raises:
            RuntimeError: If no Anthropic client has been injected.
        """
        if self._anthropic_client is None:
            raise RuntimeError(
                "Anthropic client not injected. Pass anthropic_client= to Agent()."
            )

        import anthropic as anthropic_sdk

        model_name = self._settings.anthropic_model
        client = self._anthropic_client

        def _call(**_: Any) -> anthropic_sdk.types.Message:
            """Closure that captures model, prompt, and max_tokens."""
            return client.messages.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )

        def _response_extractor(resp: anthropic_sdk.types.Message) -> str:
            return resp.content[0].text  # type: ignore[union-attr]

        def _token_extractor(
            resp: anthropic_sdk.types.Message,
        ) -> tuple[int | None, int | None]:
            return resp.usage.input_tokens, resp.usage.output_tokens

        return self._logger.log_call(
            session_id=session_id,
            user_id=user_id,
            provider=PROVIDER_ANTHROPIC,
            model=model_name,
            prompt=prompt,
            call_fn=_call,
            response_extractor=_response_extractor,
            token_extractor=_token_extractor,
        )

    def _chat_openai(
        self,
        *,
        prompt: str,
        session_id: str,
        user_id: str,
        max_tokens: int,
    ) -> str:
        """Route a call through the OpenAI Chat Completions API via AuditLogger.

        Args:
            prompt: User prompt text.
            session_id: Session identifier.
            user_id: User identifier.
            max_tokens: Max completion tokens.

        Returns:
            Model response text.

        Raises:
            RuntimeError: If no OpenAI client has been injected.
        """
        if self._openai_client is None:
            raise RuntimeError(
                "OpenAI client not injected. Pass openai_client= to Agent()."
            )

        import openai as openai_sdk

        model_name = self._settings.openai_model
        client = self._openai_client

        def _call(**_: Any) -> openai_sdk.types.chat.ChatCompletion:
            """Closure that captures model, prompt, and max_tokens."""
            return client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )

        def _response_extractor(
            resp: openai_sdk.types.chat.ChatCompletion,
        ) -> str:
            content = resp.choices[0].message.content
            return content if content is not None else ""

        def _token_extractor(
            resp: openai_sdk.types.chat.ChatCompletion,
        ) -> tuple[int | None, int | None]:
            if resp.usage is None:
                return None, None
            return resp.usage.prompt_tokens, resp.usage.completion_tokens

        return self._logger.log_call(
            session_id=session_id,
            user_id=user_id,
            provider=PROVIDER_OPENAI,
            model=model_name,
            prompt=prompt,
            call_fn=_call,
            response_extractor=_response_extractor,
            token_extractor=_token_extractor,
        )

    def _chat_llama_cpp(
        self,
        *,
        prompt: str,
        session_id: str,
        user_id: str,
        max_tokens: int,
    ) -> str:
        """Route a call through a local llama-cpp-python model via AuditLogger.

        The Llama model is loaded lazily on first use so startup cost is
        deferred until the llama_cpp provider is actually needed.

        On Apple Silicon M2 (8 GB unified memory), recommended settings
        in .env::

            LLAMA_N_GPU_LAYERS=-1   # all layers on Metal
            LLAMA_N_CTX=2048        # conservative for 8 GB unified memory
            LLAMA_N_THREADS=4

        Args:
            prompt: User prompt text.
            session_id: Session identifier.
            user_id: User identifier.
            max_tokens: Max completion tokens.

        Returns:
            Model response text.
        """
        llama = self._get_or_load_llama()
        model_path = self._settings.llama_model_path

        def _call(**_: Any) -> Any:
            """Closure that captures llama, prompt, and max_tokens."""
            return llama(prompt, max_tokens=max_tokens, echo=False)

        def _response_extractor(resp: Any) -> str:
            return str(resp["choices"][0]["text"])

        def _token_extractor(resp: Any) -> tuple[int | None, int | None]:
            usage = resp.get("usage", {})
            return usage.get("prompt_tokens"), usage.get("completion_tokens")

        return self._logger.log_call(
            session_id=session_id,
            user_id=user_id,
            provider=PROVIDER_LLAMA_CPP,
            model=model_path,
            prompt=prompt,
            call_fn=_call,
            response_extractor=_response_extractor,
            token_extractor=_token_extractor,
        )

    def _get_or_load_llama(self) -> "Llama":
        """Return the cached Llama model, loading it on first call.

        Returns:
            Loaded ``llama_cpp.Llama`` instance.
        """
        if self._llama_model is not None:
            return self._llama_model

        from llama_cpp import Llama  # deferred import — not needed for cloud providers

        log.info(
            "llama_cpp.loading_model",
            model_path=self._settings.llama_model_path,
            n_ctx=self._settings.llama_n_ctx,
            n_gpu_layers=self._settings.llama_n_gpu_layers,
        )
        self._llama_model = Llama(
            model_path=self._settings.llama_model_path,
            n_ctx=self._settings.llama_n_ctx,
            n_gpu_layers=self._settings.llama_n_gpu_layers,
            n_threads=self._settings.llama_n_threads,
            verbose=False,
        )
        return self._llama_model
