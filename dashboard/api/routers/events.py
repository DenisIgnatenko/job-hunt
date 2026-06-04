from fastapi import APIRouter, Depends, Query

from dashboard.api.auth import require_auth
from dashboard.api.models import EventOut
from src.database.repository import CommunityEventRepository

router = APIRouter(prefix="/api/events", tags=["events"])

_event_repo = CommunityEventRepository()

_ALL_STATUSES = ["new", "interested", "attending", "attended", "skipped"]


@router.get("", response_model=list[EventOut])
def list_events(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    _: str = Depends(require_auth),
) -> list[EventOut]:
    statuses = [status] if status else _ALL_STATUSES
    events = _event_repo.get_all_by_statuses(statuses)

    return [
        EventOut(
            id=e.id,  # type: ignore[arg-type]
            title=e.title,
            url=e.url,
            event_type=e.event_type,
            location=e.location,
            event_date=e.event_date,
            organizer=e.organizer,
            description=e.description,
            score=e.score,
            status=e.status,
            source=e.source,
            fetched_at=e.fetched_at,
        )
        for e in events[:limit]
        if e.id is not None
    ]
