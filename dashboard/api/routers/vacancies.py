import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dashboard.api.auth import require_auth
from dashboard.api.models import (
    CoverLetterOut,
    OutreachContactOut,
    VacancyDetailOut,
    VacancyOut,
)
from src.database.repository import (
    CoverLetterRepository,
    OutreachContactRepository,
    VacancyRepository,
)

_VALID_STATUSES = {
    "new", "in_progress", "letter_sent", "applied",
    "interview", "offer", "rejected", "rejected_by_company",
}

class StatusUpdate(BaseModel):
    status: str

class NotesUpdate(BaseModel):
    notes: str

class RegenerateLetterRequest(BaseModel):
    comments: str | None = None

router = APIRouter(prefix="/api/vacancies", tags=["vacancies"])

_vacancy_repo = VacancyRepository()
_letter_repo = CoverLetterRepository()
_outreach_repo = OutreachContactRepository()


def _to_outreach_out(c) -> OutreachContactOut:
    return OutreachContactOut(
        id=c.id,  # type: ignore[arg-type]
        full_name=c.full_name,
        headline=c.headline,
        role_category=c.role_category,
        linkedin_url=c.linkedin_url,
        source=c.source,
        message_draft=c.message_draft,
        status=c.status,
        fetched_at=c.fetched_at,
    )


@router.get("", response_model=list[VacancyOut])
def list_vacancies(
    status: str | None = Query(None),
    platform: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    _: str = Depends(require_auth),
) -> list[VacancyOut]:
    if q and q.strip():
        vacancies = _vacancy_repo.search(q.strip(), limit=200)
    elif status:
        statuses = ["in_progress", "letter_sent"] if status == "in_progress" else [status]
        vacancies = _vacancy_repo.get_all_by_statuses(statuses)
    else:
        vacancies = _vacancy_repo.get_all_by_statuses([
            "new", "in_progress", "letter_sent", "applied",
            "interview", "offer", "rejected", "rejected_by_company",
        ])

    if not q and platform:
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
            score=v.score,
            url=v.url,
            posted_at=v.posted_at,
            fetched_at=v.fetched_at,
        )
        for v in (vacancies if q else vacancies[:limit])
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
        score=v.score,
        url=v.url,
        posted_at=v.posted_at,
        fetched_at=v.fetched_at,
        description=v.description,
        company_report=v.company_report,
        match_analysis=v.match_analysis,
        notes=v.notes,
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
        outreach_contacts=[
            _to_outreach_out(c) for c in _outreach_repo.get_by_vacancy(vacancy_id) if c.id is not None
        ],
    )


@router.patch("/{vacancy_id}/status")
def update_status(
    vacancy_id: int,
    body: StatusUpdate,
    _: str = Depends(require_auth),
) -> dict:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    if not _vacancy_repo.get_by_id(vacancy_id):
        raise HTTPException(status_code=404, detail="Vacancy not found")
    _vacancy_repo.update_status(vacancy_id, body.status)
    return {"ok": True}


@router.patch("/{vacancy_id}/notes")
def update_notes(
    vacancy_id: int,
    body: NotesUpdate,
    _: str = Depends(require_auth),
) -> dict:
    if not _vacancy_repo.get_by_id(vacancy_id):
        raise HTTPException(status_code=404, detail="Vacancy not found")
    _vacancy_repo.save_notes(vacancy_id, body.notes)
    return {"ok": True}


@router.post("/{vacancy_id}/generate-letter")
async def generate_letter(
    vacancy_id: int,
    _: str = Depends(require_auth),
) -> dict:
    """
    Запускает research + letter pipeline в отдельном потоке.
    Блокирует запрос на 15-30 секунд — frontend показывает loading.
    """
    from dashboard.api.pipeline import run_research_pipeline

    if not _vacancy_repo.get_by_id(vacancy_id):
        raise HTTPException(status_code=404, detail="Vacancy not found")

    body = await asyncio.to_thread(run_research_pipeline, vacancy_id)
    return {"body": body}


@router.post("/{vacancy_id}/regenerate-letter")
async def regenerate_letter(
    vacancy_id: int,
    body: RegenerateLetterRequest,
    _: str = Depends(require_auth),
) -> dict:
    """Пересоздаёт письмо (без research) с опциональным фидбеком пользователя."""
    from dashboard.api.pipeline import regenerate_letter as regen

    if not _vacancy_repo.get_by_id(vacancy_id):
        raise HTTPException(status_code=404, detail="Vacancy not found")

    letter_body = await asyncio.to_thread(regen, vacancy_id, body.comments)
    return {"body": letter_body}


@router.post("/{vacancy_id}/company-report")
async def company_report(
    vacancy_id: int,
    _: str = Depends(require_auth),
) -> dict:
    """Генерирует AI отчёт о компании для кандидата."""
    from dashboard.api.pipeline import generate_company_report
    if not _vacancy_repo.get_by_id(vacancy_id):
        raise HTTPException(status_code=404, detail="Vacancy not found")
    report = await asyncio.to_thread(generate_company_report, vacancy_id)
    return {"report": report}


@router.post("/{vacancy_id}/match-analysis")
async def match_analysis(
    vacancy_id: int,
    _: str = Depends(require_auth),
) -> dict:
    """AI анализ совпадения вакансии с резюме Denis."""
    from dashboard.api.pipeline import generate_match_analysis
    if not _vacancy_repo.get_by_id(vacancy_id):
        raise HTTPException(status_code=404, detail="Vacancy not found")
    analysis = await asyncio.to_thread(generate_match_analysis, vacancy_id)
    return {"analysis": analysis}


@router.post("/{vacancy_id}/find-outreach-contacts", response_model=list[OutreachContactOut])
async def find_outreach_contacts(
    vacancy_id: int,
    _: str = Depends(require_auth),
) -> list[OutreachContactOut]:
    """
    Ищет людей (техлиды, HR) в компании этой вакансии: ddgs, LinkedIn people search
    как fallback. Найденное сохраняется в БД, дедуп по linkedin_url — повторный клик
    не плодит дубликаты, просто возвращает актуальный список.
    """
    from dashboard.api.pipeline import find_outreach_contacts as find_contacts

    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    contacts = await asyncio.to_thread(find_contacts, vacancy_id)
    return [_to_outreach_out(c) for c in contacts if c.id is not None]
