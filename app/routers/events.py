"""Event-related API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import verify_token
from app.models import Event
from app.schemas import EventCreate, EventResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    event: EventCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """
    Record a new event.

    Events must include user_id, event_type, and optionally timestamp and properties.
    If timestamp is not provided, the current time is used.
    """
    db_event = Event(
        user_id=event.user_id,
        event_type=event.event_type,
        timestamp=event.timestamp or datetime.utcnow(),
        properties=event.properties,
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    return db_event


@router.get("", response_model=list[EventResponse])
def list_events(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """
    List events with optional filters.

    Supports filtering by user_id, event_type, and date range.
    Results are paginated with limit and offset parameters.
    """
    query = db.query(Event)

    if user_id:
        query = query.filter(Event.user_id == user_id)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if start_date:
        query = query.filter(Event.timestamp >= start_date)
    if end_date:
        query = query.filter(Event.timestamp <= end_date)

    query = query.order_by(Event.timestamp.desc())
    query = query.offset(offset).limit(limit)

    return query.all()
