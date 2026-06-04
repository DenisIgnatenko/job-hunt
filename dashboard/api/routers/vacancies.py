from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.api.auth import require_auth
from dashboard.api.models import VacancyDetailOut, VacancyOut, CoverLetterOut
from src.database.repository import CoverLetterRepository, VacancyRepository

router = APIRouter(prefix="/api/vacancies", tags=["vacancies"])

_vacancy_repo = VacancyRepository()
_letter_repo = CoverLetterRepository()


@router.get("", response_model=list[VacancyOut])
def list_vacancies(
    status: str | None = Query(None),
    platform: str | None = Query(None),
    limit: int = Query(50, le=200),
    _: str = Depends(require_auth),
) -> list[VacancyOut]:
    if status:
        vacancies = _vacancy_repo.get_all_by_statuses([status])
    else:
        vacancies = _vacancy_repo.get_all_by_statuses([
            "new", "in_progress", "letter_sent", "applied",
            "interview", "offer", "rejected", "rejected_by_company",
        ])

    if platform:
        vacancies = [v for v in vacancies if v.platform == platform]

    return [
        VacancyOut(
            id=v.id,  # type: ignore[arg-type]
            title=v.title,
            company=v.company,
            location=v.location,
            city=v.city,
            platform=v.platform,
            work_format=v.work_format,
            status=v.status,
            url=v.url,
            posted_at=v.posted_at,
            fetched_at=v.fetched_at,
        )
        for v in vacancies[:limit]
        if v.id is not None
    ]


@router.get("/{vacancy_id}", response_model=VacancyDetailOut)
def get_vacancy(
    vacancy_id: int,
    _: str = Depends(require_auth),
) -> VacancyDetailOut:
    v = _vacancy_repo.get_by_id(vacancy_id)
    if not v:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    letters = _letter_repo.get_by_vacancy(vacancy_id)

    return VacancyDetailOut(
        id=v.id,  # type: ignore[arg-type]
        title=v.title,
        company=v.company,
        location=v.location,
        city=v.city,
        platform=v.platform,
        work_format=v.work_format,
        status=v.status,
        url=v.url,
        posted_at=v.posted_at,
        fetched_at=v.fetched_at,
        description=v.description,
        cover_letters=[
            CoverLetterOut(
                id=l.id,  # type: ignore[arg-type]
                body=l.body,
                version=l.version,
                approved=l.approved,
                created_at=l.created_at,
            )
            for l in letters
            if l.id is not None
        ],
    )
