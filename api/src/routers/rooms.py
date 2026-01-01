"""Room endpoints for multi-room support."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..db import get_db, Room, Message, RoomMember
from ..auth import get_current_session
from ..schemas.room import RoomListResponse, RoomListItem, RoomDetail

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=RoomListResponse)
async def list_rooms(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_session),
):
    """List all rooms for the room selector dropdown."""
    # Get room stats with aggregated data
    rooms_with_stats = (
        db.query(
            Room.id,
            Room.name,
            Room.avatar_url,
            Room.description,
            Room.display_order,
            func.count(Message.id).label("message_count"),
            func.max(Message.timestamp).label("last_message_at"),
        )
        .outerjoin(Message, Room.id == Message.room_id)
        .group_by(Room.id)
        .order_by(Room.display_order, Room.id)
        .all()
    )
    
    # Get member counts separately (more efficient)
    member_counts = dict(
        db.query(RoomMember.room_id, func.count(RoomMember.id))
        .group_by(RoomMember.room_id)
        .all()
    )
    
    rooms = [
        RoomListItem(
            id=r.id,
            name=r.name,
            avatar_url=r.avatar_url,
            description=r.description,
            display_order=r.display_order or 0,
            message_count=r.message_count or 0,
            member_count=member_counts.get(r.id, 0),
            last_message_at=r.last_message_at,
        )
        for r in rooms_with_stats
    ]
    
    return RoomListResponse(rooms=rooms)


@router.get("/first", response_model=RoomDetail)
async def get_first_room(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_session),
):
    """Get the first room (for redirects). Returns 404 if no rooms exist."""
    room = db.query(Room).order_by(Room.display_order, Room.id).first()
    if not room:
        raise HTTPException(status_code=404, detail="No rooms found")
    
    # Get message stats
    message_stats = (
        db.query(
            func.count(Message.id).label("count"),
            func.min(Message.timestamp).label("first_at"),
            func.max(Message.timestamp).label("last_at"),
        )
        .filter(Message.room_id == room.id)
        .first()
    )
    
    # Get member count
    member_count = (
        db.query(func.count(RoomMember.id))
        .filter(RoomMember.room_id == room.id)
        .scalar()
    ) or 0
    
    return RoomDetail(
        id=room.id,
        matrix_room_id=room.matrix_room_id,
        name=room.name,
        avatar_url=room.avatar_url,
        description=room.description,
        is_group=room.is_group,
        display_order=room.display_order or 0,
        message_count=message_stats.count or 0,
        member_count=member_count,
        first_message_at=message_stats.first_at,
        last_message_at=message_stats.last_at,
        created_at=room.created_at,
    )


@router.get("/{room_id}", response_model=RoomDetail)
async def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_session),
):
    """Get detailed information about a specific room."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get message stats
    message_stats = (
        db.query(
            func.count(Message.id).label("count"),
            func.min(Message.timestamp).label("first_at"),
            func.max(Message.timestamp).label("last_at"),
        )
        .filter(Message.room_id == room_id)
        .first()
    )
    
    # Get member count
    member_count = (
        db.query(func.count(RoomMember.id))
        .filter(RoomMember.room_id == room_id)
        .scalar()
    ) or 0
    
    return RoomDetail(
        id=room.id,
        matrix_room_id=room.matrix_room_id,
        name=room.name,
        avatar_url=room.avatar_url,
        description=room.description,
        is_group=room.is_group,
        display_order=room.display_order or 0,
        message_count=message_stats.count or 0,
        member_count=member_count,
        first_message_at=message_stats.first_at,
        last_message_at=message_stats.last_at,
        created_at=room.created_at,
    )
