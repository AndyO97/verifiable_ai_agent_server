"""Configuration validation tests for malformed critical environment values."""

import pytest
from pydantic import ValidationError

from src.config import OllamaSettings


def test_settings_fail_on_invalid_ollama_max_tokens(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MAX_TOKENS", "not-a-number")
    with pytest.raises(ValidationError):
        OllamaSettings()


def test_settings_fail_on_invalid_ollama_temperature(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "not-a-float")
    with pytest.raises(ValidationError):
        OllamaSettings()


def test_settings_parse_valid_numeric_config(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MAX_TOKENS", "1234")
    settings = OllamaSettings()
    assert settings.max_tokens == 1234
