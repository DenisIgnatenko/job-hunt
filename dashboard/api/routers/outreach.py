"""
Contact-scoped outreach endpoints (SRP): всё, что адресуется по contact_id,
не по vacancy_id — draft-message и status. Поиск контактов (vacancy-scoped)
живёт в vacancies.py, рядом с generate-letter / company-report / match-analysis
(тот же прецедент, что уже устоялся в этом роутере).
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dashboard.api.auth import require_auth
from src.database.repository import OutreachContactRepository

router = APIRouter(prefix="/api/outreach", tags=["outreach"])

_outreach_repo = OutreachContactRepository()

_VALID_STATUSES = {"new", "drafted", "sent", "replied", "skipped"}


class OutreachStatusUpdate(BaseModel):
    status: str


@router.post("/{contact_id}/draft-message")
async def draft_message(
    contact_id: int,
    _: str = Depends(require_auth),
) -> dict:
    """Генерирует LinkedIn connection-request note. Denis отправляет вручную."""
    from dashboard.api.pipeline import draft_outreach_message

    if not _outreach_repo.get_by_id(contact_id):
        raise HTTPException(status_code=404, detail="Outreach contact not found")

    message = await asyncio.to_thread(draft_outreach_message, contact_id)
    return {"message": message}


@router.patch("/{contact_id}/status")
def update_status(
    contact_id: int,
    body: OutreachStatusUpdate,
    _: str = Depends(require_auth),
) -> dict:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    if not _outreach_repo.get_by_id(contact_id):
        raise HTTPException(status_code=404, detail="Outreach contact not found")
    _outreach_repo.update_status(contact_id, body.status)
    return {"ok": True}
