"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "UpApply API"
    debug: bool = False
    environment: str = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 10000

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/upapply"

    @field_validator("database_url", mode="before")
    @classmethod
    def transform_database_url(cls, v: str) -> str:
        """Transform Render's postgres:// URL to asyncpg format."""
        if not v:
            return v
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # CORS - use ["*"] to allow chrome extensions with dynamic IDs
    cors_origins: List[str] = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v

    # Monitoring
    sentry_dsn: str = ""
    resend_api_key: str = ""
    alert_email: str = "info@servicevision.io"

    # AI
    openai_api_key: str = ""
    default_model: str = "gpt-4.1-nano"
    scoring_model: str = "gpt-4.1-nano"   # job scoring — cheap structured extraction
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    cover_letter_model: str = "claude-sonnet-4-6"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    @field_validator("anthropic_api_key", mode="after")
    @classmethod
    def warn_if_anthropic_key_missing(cls, v: str) -> str:
        """Emit a startup warning when the Anthropic key is absent.

        Cover letter generation will fail at request time, but the server
        should still start so other endpoints remain available.
        """
        if not v:
            import warnings
            warnings.warn(
                "ANTHROPIC_API_KEY is not set — cover letter generation will be unavailable.",
                RuntimeWarning,
                stacklevel=2,
            )
        return v

    @field_validator("secret_key", mode="after")
    @classmethod
    def check_secret_key_in_production(cls, v: str, info) -> str:
        """Prevent default secret key in production."""
        env = info.data.get("environment", "development")
        if env == "production" and v == "dev-secret-key-change-in-production":
            raise ValueError(
                "SECRET_KEY must be changed from default in production. "
                "Set the SECRET_KEY environment variable."
            )
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
