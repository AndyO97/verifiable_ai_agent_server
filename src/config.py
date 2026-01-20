"""
Configuration management for the verifiable AI agent server
"""

from typing import Optional

from pydantic_settings import BaseSettings


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings"""
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str
    database: str = "verifiable_agent"
    
    class Config:
        env_prefix = "POSTGRES_"


class LocalStorageSettings(BaseSettings):
    """Local file system storage settings"""
    base_path: str = "./artifacts"
    
    class Config:
        env_prefix = "LOCAL_STORAGE_"


class OllamaSettings(BaseSettings):
    """Ollama LLM settings"""
    base_url: str = "http://localhost:11434"
    model: str = "mistral"
    temperature: float = 0.7
    max_tokens: int = 2000
    
    class Config:
        env_prefix = "OLLAMA_"
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env


class OpenRouterSettings(BaseSettings):
    """OpenRouter.ai LLM settings"""
    api_key: Optional[str] = None  # From OPENROUTER_API_KEY env var
    model: str = "mistralai/devstral-2512:free"  # Free Devstral 2512 model
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.3  # Lower temperature for more deterministic behavior
    max_tokens: int = 4000  # Increased for better tool call generation
    
    class Config:
        env_prefix = "OPENROUTER_"
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env


class S3Settings(BaseSettings):
    """AWS S3 settings for artifact storage"""
    endpoint_url: Optional[str] = None
    access_key_id: str
    secret_access_key: str
    bucket: str = "verifiable-agent-logs"
    region: str = "us-east-1"
    
    class Config:
        env_prefix = "S3_"


class LangfuseSettings(BaseSettings):
    """Langfuse self-hosted settings"""
    api_endpoint: str = "http://localhost:3000"
    public_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    class Config:
        env_prefix = "LANGFUSE_"


class OTelSettings(BaseSettings):
    """OpenTelemetry configuration"""
    otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "verifiable-ai-agent"
    service_version: str = "0.1.0"
    
    class Config:
        env_prefix = "OTEL_"


class Settings(BaseSettings):
    """Main application settings"""
    # Environment
    environment: str = "development"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Crypto
    session_timeout_seconds: int = 3600
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or initialize global settings"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
