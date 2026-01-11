"""SQLAlchemy implementation of EventRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Event
from app.repositories.interfaces import (
    EventRepository,
    EventEntity,
    EventInput,
    EventFilter,
)


class SQLAlchemyEventRepository(EventRepository):
    """SQLAlchemy implementation of event repository."""

    def __init__(self, session: Session):
        self._session = session

    def _to_entity(self, model: Event) -> EventEntity:
        """Convert SQLAlchemy model to entity."""
        return EventEntity(
            id=model.id,
            user_id=model.user_id,
            event_type=model.event_type,
            timestamp=model.timestamp,
            properties=model.properties,
        )

    def create(self, data: EventInput) -> EventEntity:
        """Create a new event."""
        model = Event(
            user_id=data.user_id,
            event_type=data.event_type,
            timestamp=data.timestamp or datetime.utcnow(),
            properties=data.properties,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)

        return self._to_entity(model)

    def list(self, filter: EventFilter) -> list[EventEntity]:
        """List events with optional filters."""
        query = self._session.query(Event)

        if filter.user_id:
            query = query.filter(Event.user_id == filter.user_id)
        if filter.event_type:
            query = query.filter(Event.event_type == filter.event_type)
        if filter.start_date:
            query = query.filter(Event.timestamp >= filter.start_date)
        if filter.end_date:
            query = query.filter(Event.timestamp <= filter.end_date)

        query = query.order_by(Event.timestamp.desc())
        query = query.offset(filter.offset).limit(filter.limit)

        return [self._to_entity(m) for m in query.all()]

    def get_events_for_user_after(
        self,
        user_id: str,
        after: datetime,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[EventEntity]:
        """Get events for a user after a specific timestamp."""
        query = self._session.query(Event).filter(
            Event.user_id == user_id,
            Event.timestamp > after,
        )

        if event_type:
            query = query.filter(Event.event_type == event_type)
        if start_date:
            query = query.filter(Event.timestamp >= start_date)
        if end_date:
            query = query.filter(Event.timestamp <= end_date)

        return [self._to_entity(m) for m in query.all()]
