"""Room schemas for API responses."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class RoomBase(BaseModel):
    """Base room schema."""
    id: int
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    description: Optional[str] = None


class RoomListItem(RoomBase):
    """Room item for dropdown/list views."""
    message_count: int = 0
    member_count: int = 0
    last_message_at: Optional[datetime] = None
    display_order: int = 0


class RoomListResponse(BaseModel):
    """Response for listing all rooms."""
    rooms: List[RoomListItem]


class RoomDetail(RoomBase):
    """Detailed room info."""
    matrix_room_id: str
    is_group: bool = True
    message_count: int = 0
    member_count: int = 0
    last_message_at: Optional[datetime] = None
    first_message_at: Optional[datetime] = None
    created_at: datetime
    display_order: int = 0


class RoomMemberStats(BaseModel):
    """Per-room stats for a person."""
    room_id: int
    room_name: Optional[str] = None
    message_count: int = 0
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class PersonRoomsResponse(BaseModel):
    """Response for getting rooms a person is in."""
    rooms: List[RoomMemberStats]
