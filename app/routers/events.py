"""Event-related API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.auth import verify_token
from app.dependencies import get_event_repository
from app.repositories.interfaces import EventRepository, EventInput, EventFilter
from app.schemas import EventCreate, EventResponse

router = APIRouter(prefix="/events", tags=["events"])


def _to_event_response(entity) -> EventResponse:
    """Convert EventEntity to EventResponse."""
    return EventResponse(
        id=entity.id,
        user_id=entity.user_id,
        event_type=entity.event_type,
        timestamp=entity.timestamp,
        properties=entity.properties,
    )


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    event: EventCreate,
    repo: EventRepository = Depends(get_event_repository),
    _: str = Depends(verify_token),
):
    """
    Record a new event.

    Events must include user_id, event_type, and optionally timestamp and properties.
    If timestamp is not provided, the current time is used.
    """
    data = EventInput(
        user_id=event.user_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        properties=event.properties,
    )
    entity = repo.create(data)
    return _to_event_response(entity)


@router.get("", response_model=list[EventResponse])
def list_events(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    repo: EventRepository = Depends(get_event_repository),
    _: str = Depends(verify_token),
):
    """
    List events with optional filters.

    Supports filtering by user_id, event_type, and date range.
    Results are paginated with limit and offset parameters.
    """
    filter = EventFilter(
        user_id=user_id,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    entities = repo.list(filter)
    return [_to_event_response(e) for e in entities]
