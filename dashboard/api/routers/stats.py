from fastapi import APIRouter, Depends

from dashboard.api.auth import require_auth
from dashboard.api.models import StatsOut
from src.database.schema import get_connection

router = APIRouter(prefix="/api/stats", tags=["stats"])

_VACANCY_STATUSES = [
    "new", "in_progress", "letter_sent", "applied",
    "interview", "offer", "rejected", "rejected_by_company",
]
_EVENT_STATUSES = ["new", "interested", "attending", "attended", "skipped"]


@router.get("", response_model=StatsOut)
def get_stats(_: str = Depends(require_auth)) -> StatsOut:
    with get_connection() as conn:
        # Вакансии по статусу
        vacancies: dict[str, int] = {s: 0 for s in _VACANCY_STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) FROM vacancies GROUP BY status"):
            if row[0] in vacancies:
                vacancies[row[0]] = row[1]

        # События по статусу
        events: dict[str, int] = {s: 0 for s in _EVENT_STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) FROM community_events GROUP BY status"):
            if row[0] in events:
                events[row[0]] = row[1]

        # Вакансии по платформе
        platforms: dict[str, int] = {}
        for row in conn.execute("SELECT platform, COUNT(*) FROM vacancies GROUP BY platform"):
            platforms[row[0]] = row[1]

    return StatsOut(vacancies=vacancies, events=events, platforms=platforms)
