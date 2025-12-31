from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Archive service settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )
    
    database_url: str = "postgresql://archive:archivepass123@postgres:5432/messenger_archive"
    matrix_homeserver_url: str = "http://synapse:8008"
    matrix_user_id: str = "@archive:archive.local"
    matrix_password: str = "archivepass123"
    
    # Room name to archive (partial match, case-insensitive)
    # Leave empty to archive all rooms
    archive_room_filter: Optional[str] = "General Chat - Manila Dialectics Society"
    
    # API URL for embedding service
    api_url: str = "http://api:8000"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
