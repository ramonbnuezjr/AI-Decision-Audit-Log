"""Unit tests for src/config.py — Settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


class TestSettings:
    def test_defaults_are_safe(self) -> None:
        s = Settings()
        assert s.environment == "local"
        assert s.log_level == "INFO"
        assert s.hardware_enabled is False

    def test_log_level_uppercased(self) -> None:
        s = Settings(log_level="debug")
        assert s.log_level == "DEBUG"

    def test_invalid_log_level_raises(self) -> None:
        with pytest.raises(ValidationError, match="log_level"):
            Settings(log_level="VERBOSE")

    def test_invalid_environment_raises(self) -> None:
        with pytest.raises(ValidationError, match="environment"):
            Settings(environment="development")

    def test_environment_lowercased(self) -> None:
        s = Settings(environment="PRODUCTION")
        assert s.environment == "production"

    def test_all_valid_environments(self) -> None:
        for env in ("local", "staging", "production"):
            s = Settings(environment=env)
            assert s.environment == env

    def test_all_valid_log_levels(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            s = Settings(log_level=level)
            assert s.log_level == level

    def test_custom_values_stored(self) -> None:
        s = Settings(
            anthropic_api_key="sk-ant-test",
            audit_store_path="/tmp/test.db",
            llama_n_ctx=2048,
            llama_n_gpu_layers=0,
        )
        assert s.anthropic_api_key == "sk-ant-test"
        assert s.audit_store_path == "/tmp/test.db"
        assert s.llama_n_ctx == 2048
        assert s.llama_n_gpu_layers == 0

    def test_get_settings_returns_settings_instance(self) -> None:
        s = get_settings()
        assert isinstance(s, Settings)
