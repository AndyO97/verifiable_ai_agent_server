"""
Configuration management for the verifiable AI agent server
"""

from typing import Optional

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings"""
    model_config = ConfigDict(env_prefix="POSTGRES_")
    
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str
    database: str = "verifiable_agent"


class LocalStorageSettings(BaseSettings):
    """Local file system storage settings"""
    model_config = ConfigDict(env_prefix="LOCAL_STORAGE_")
    
    base_path: str = "./artifacts"


class OllamaSettings(BaseSettings):
    """Ollama LLM settings"""
    model_config = ConfigDict(env_prefix="OLLAMA_", env_file=".env", case_sensitive=False, extra="ignore")
    
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    temperature: float = 0.7
    max_tokens: int = 2000


class OpenRouterSettings(BaseSettings):
    """OpenRouter.ai LLM settings"""
    model_config = ConfigDict(env_prefix="OPENROUTER_", env_file=".env", case_sensitive=False, extra="ignore")
    
    api_key: Optional[str] = None  # From OPENROUTER_API_KEY env var
    model: str = "arcee-ai/trinity-large-preview:free"  # Default matches .env
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.3  # Lower temperature for more deterministic behavior
    max_tokens: int = 4000  # Increased for better tool call generation


class S3Settings(BaseSettings):
    """AWS S3 settings for artifact storage"""
    model_config = ConfigDict(env_prefix="S3_")
    
    endpoint_url: Optional[str] = None
    access_key_id: str
    secret_access_key: str
    bucket: str = "verifiable-agent-logs"
    region: str = "us-east-1"


class LangfuseSettings(BaseSettings):
    """Langfuse self-hosted settings"""
    model_config = ConfigDict(env_prefix="LANGFUSE_", env_file=".env", case_sensitive=False, extra="ignore")
    
    api_endpoint: str = "http://localhost:3000"
    public_key: Optional[str] = None
    secret_key: Optional[str] = None


class OTelSettings(BaseSettings):
    """OpenTelemetry configuration"""
    model_config = ConfigDict(env_prefix="OTEL_")
    
    otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "verifiable-ai-agent"
    service_version: str = "0.1.0"


class SecuritySettings(BaseSettings):
    """Security and Cryptography settings"""
    model_config = ConfigDict(env_prefix="SECURITY_", env_file=".env", case_sensitive=False, extra="ignore")
    
    # Hex-encoded 32-byte master secret key.
    # If not provided, a random ephemeral key will be generated.
    master_secret_key: Optional[str] = None



class OpenWeatherSettings(BaseSettings):
    """OpenWeatherMap API settings"""
    model_config = ConfigDict(env_prefix="OPENWEATHER_", env_file=".env", case_sensitive=False, extra="ignore")
    api_key: Optional[str] = None  # From OPENWEATHER_API_KEY
    base_url: str = "https://api.openweathermap.org/data/2.5"


class Settings(BaseSettings):
    """Main application settings"""
    model_config = ConfigDict(env_file=".env", case_sensitive=False)
    
    # Environment
    environment: str = "development"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # LLM provider selection: "ollama" (default) or "openrouter"
    llm_provider: str = "ollama"
    
    # Crypto
    session_timeout_seconds: int = 3600
    security: SecuritySettings = SecuritySettings()
    
    # Storage (default: local file system)
    storage_backend: str = "local"  # Options: "local", "s3", "azure"
    local_storage: LocalStorageSettings = LocalStorageSettings()
    s3: Optional[S3Settings] = None
    
    # LLM (choose one: ollama or openrouter)
    ollama: OllamaSettings = OllamaSettings()
    openrouter: OpenRouterSettings = OpenRouterSettings()
    
    # Observability
    langfuse: LangfuseSettings = LangfuseSettings()
    otel: OTelSettings = OTelSettings()
    
    # OpenWeather
    openweather: OpenWeatherSettings = OpenWeatherSettings()


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or initialize global settings"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
