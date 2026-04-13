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


@pytest.mark.parametrize("value", ["0", "-1", "32769"])
def test_settings_fail_on_out_of_range_ollama_max_tokens(monkeypatch, value: str) -> None:
    monkeypatch.setenv("OLLAMA_MAX_TOKENS", value)
    with pytest.raises(ValidationError):
        OllamaSettings()


@pytest.mark.parametrize("value", ["1", "32768"])
def test_settings_accept_ollama_max_tokens_boundary_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("OLLAMA_MAX_TOKENS", value)
    settings = OllamaSettings()
    assert settings.max_tokens == int(value)


@pytest.mark.parametrize("value", ["-0.01", "1.01"])
def test_settings_fail_on_out_of_range_ollama_temperature(monkeypatch, value: str) -> None:
    monkeypatch.setenv("OLLAMA_TEMPERATURE", value)
    with pytest.raises(ValidationError):
        OllamaSettings()


@pytest.mark.parametrize("value", ["0", "1"])
def test_settings_accept_ollama_temperature_boundary_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("OLLAMA_TEMPERATURE", value)
    settings = OllamaSettings()
    assert settings.temperature == float(value)


@pytest.mark.parametrize("value", ["0", "-1", "601"])
def test_settings_fail_on_out_of_range_ollama_timeout(monkeypatch, value: str) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        OllamaSettings()


@pytest.mark.parametrize("value", ["1", "600"])
def test_settings_accept_ollama_timeout_boundary_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", value)
    settings = OllamaSettings()
    assert settings.timeout_seconds == int(value)
