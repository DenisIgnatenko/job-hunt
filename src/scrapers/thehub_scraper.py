"""
The Hub (thehub.io) scraper — главный датский tech job board (SRP, OCP).

API endpoint: https://thehub.io/api/jobs
Реальные рабочие параметры (проверено):
  search=<keyword>   — fulltext поиск по названию/описанию
  countryCode=DK     — только датские позиции
  isRemote=true      — remote позиции
  limit=<n>          — кол-во результатов

Ключи в ответе:
  docs[]             — массив вакансий (не "jobs")
  absoluteJobUrl     — URL вакансии на thehub.io
  company.name       — название компании
  location.address   — адрес/город
  isRemote           — bool

Pre-filter по title через _is_tech_title() — не тратим токены на нерелевантные позиции.
"""

import logging

import requests

from src.agents.scout_agent import _is_tech_title
from src.database.repository import Vacancy
from src.scrapers.base_scraper import BaseScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://thehub.io/api/jobs"
_TIMEOUT_SEC = 15
_LIMIT_PER_SEARCH = 50

# Три поиска: два по ключевым словам в Дании + один remote worldwide
_SEARCHES = [
    {"search": "backend developer",    "countryCode": "DK", "limit": _LIMIT_PER_SEARCH},
    {"search": "software engineer",    "countryCode": "DK", "limit": _LIMIT_PER_SEARCH},
    {"search": "backend developer",    "isRemote": "true",  "limit": 30},
]


class TheHubScraper(BaseScraper):
    def fetch(self) -> list[Vacancy]:
        seen: set[str] = set()
        vacancies: list[Vacancy] = []

        for params in _SEARCHES:
            try:
                resp = requests.get(_BASE_URL, params=params, timeout=_TIMEOUT_SEC)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                log.exception("TheHub: request failed for params %s", params)
                continue

            docs: list[dict] = data.get("docs", [])
            for job in docs:
                v = self._to_vacancy(job)
                if v and v.source_id not in seen:
                    seen.add(v.source_id)
                    vacancies.append(v)

        # Pre-filter по title — экономия токенов (cheap check before expensive LLM call)
        filtered = [v for v in vacancies if _is_tech_title(v.title)]
        log.info(
            "TheHub: fetched %d vacancies, %d passed title filter",
            len(vacancies), len(filtered),
        )
        return filtered

    def _to_vacancy(self, job: dict) -> Vacancy | None:
        job_id = job.get("id") or job.get("_id")
        title = (job.get("title") or "").strip()
        url = job.get("absoluteJobUrl") or ""
        if not job_id or not title or not url:
            return None

        # company — объект {"id": "...", "name": "...", "key": "..."}
        company_raw = job.get("company") or {}
        company: str | None = company_raw.get("name") if isinstance(company_raw, dict) else None

        # location — объект {"address": "Copenhagen, Denmark", "locality": "Copenhagen", ...}
        location_raw = job.get("location") or {}
        location: str | None = None
        if isinstance(location_raw, dict):
            location = location_raw.get("address") or location_raw.get("locality")
        if not location:
            # Fallback: если нет адреса — берём countryCode или Remote
            is_remote = job.get("isRemote", False)
            location = "Remote" if is_remote else job.get("countryCode") or "Denmark"

        description = (job.get("description") or "")[:2000]

        # isRemote приходит как bool из API — используем напрямую, не ждём LLM
        work_format = "remote" if job.get("isRemote") else "unknown"

        return Vacancy(
            source_id=f"thehub_{job_id}",
            title=title,
            url=url,
            company=company,
            location=location,
            description=description,
            platform="thehub",
            work_format=work_format,
        )
