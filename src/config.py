"""Runtime configuration loaded once at startup via pydantic-settings."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced exclusively from environment variables.

    All secrets and runtime parameters are read from the process environment
    or a .env file.  No defaults expose credentials; required fields raise
    a clear ValidationError at startup when absent.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Anthropic -----------------------------------------------------------
    anthropic_api_key: str = Field(default="", description="Anthropic API key.")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Default Anthropic model identifier.",
    )

    # -- OpenAI --------------------------------------------------------------
    openai_api_key: str = Field(default="", description="OpenAI API key.")
    openai_model: str = Field(
        default="gpt-4o",
        description="Default OpenAI model identifier.",
    )

    # -- llama.cpp (local inference) -----------------------------------------
    llama_model_path: str = Field(
        default="./models/llama3.gguf",
        description="Path to the local .gguf model file for llama-cpp-python.",
    )
    llama_n_ctx: int = Field(
        default=4096,
        description="Context window size in tokens for llama.cpp.",
    )
    llama_n_gpu_layers: int = Field(
        default=-1,
        description="Layers to offload to Metal GPU. -1 = all layers.",
    )
    llama_n_threads: int = Field(
        default=4,
        description="CPU threads used by llama.cpp.",
    )

    # -- Audit store ---------------------------------------------------------
    audit_store_path: str = Field(
        default="./data/audit.db",
        description="Path to the SQLite audit database file.",
    )

    # -- Runtime -------------------------------------------------------------
    environment: str = Field(
        default="local",
        description="Runtime environment: local | staging | production.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging verbosity: DEBUG | INFO | WARNING | ERROR.",
    )
    hardware_enabled: bool = Field(
        default=False,
        description="Set true only when running on Raspberry Pi hardware.",
    )

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        """Ensure log_level is a recognised stdlib level."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got {v!r}")
        return upper

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        """Ensure environment is a recognised value."""
        allowed = {"local", "staging", "production"}
        lower = v.lower()
        if lower not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got {v!r}")
        return lower


def get_settings() -> Settings:
    """Return a Settings instance loaded from the environment.

    Returns:
        Fully validated Settings object.
    """
    return Settings()
