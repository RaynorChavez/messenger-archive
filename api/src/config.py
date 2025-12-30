from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )
    
    # Database
    database_url: str = "postgresql://archive:password@localhost:5432/messenger_archive"
    
    # Auth
    archive_password_hash: str = ""
    session_secret: str = "dev-secret-change-in-production"
    session_expire_hours: int = 24 * 7  # 1 week
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # AI (Gemini)
    gemini_api_key: str = ""
    gemini_rate_limit_tokens_per_min: int = 800_000


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
