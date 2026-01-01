from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional, List


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
    
    # Room names to archive (exact match, case-insensitive)
    # Comma-separated list. Leave empty to archive all rooms.
    archive_room_filter: Optional[str] = "General Chat - Manila Dialectics Society,Immersion - Manila Dialectics Society"
    
    # API URL for embedding service
    api_url: str = "http://api:8000"
    
    def get_room_filters(self) -> List[str]:
        """Get list of room name filters (exact match)."""
        if not self.archive_room_filter:
            return []
        return [f.strip().lower() for f in self.archive_room_filter.split(",") if f.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
