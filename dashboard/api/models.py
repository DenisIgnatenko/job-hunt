"""
Pydantic модели для API ответов (SRP: отделяем контракт API от DB dataclasses).
"""

from pydantic import BaseModel


class VacancyOut(BaseModel):
    id: int
    title: str
    company: str | None
    location: str | None
    city: str | None
    platform: str
    work_format: str
    status: str
    score: int | None = None   # ScoutAgent score 1-10, NULL для старых вакансий (до V13)
    url: str
    posted_at: str | None
    fetched_at: str | None


class CoverLetterOut(BaseModel):
    id: int
    body: str
    version: int
    approved: bool
    created_at: str | None


class VacancyDetailOut(VacancyOut):
    description: str | None
    cover_letters: list[CoverLetterOut] = []
    company_report: str | None = None
    match_analysis: str | None = None
    notes: str | None = None


class EventOut(BaseModel):
    id: int
    title: str
    url: str
    event_type: str
    location: str | None
    event_date: str | None
    organizer: str | None
    description: str | None
    score: int
    status: str
    source: str
    category: str
    fetched_at: str | None


class StatsOut(BaseModel):
    vacancies: dict[str, int]   # status -> count
    events: dict[str, int]      # status -> count
    platforms: dict[str, int]   # platform -> count of all vacancies
