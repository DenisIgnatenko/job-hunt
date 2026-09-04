"""
The Hub (thehub.io) scraper — главный датский tech job board (SRP, OCP).

API endpoint: https://thehub.io/api/v2/jobs
FIX (04.09.2026): старый /api/jobs стал отдавать 404 — TheHub перевёл поиск на v2.
Заодно поменялась форма ответа: пропали absoluteJobUrl и description.
  - URL восстанавливаем сами: https://thehub.io/jobs/{id} (проверено по HTML листинга).
  - description достаём отдельным запросом со страницы вакансии — там есть
    JSON-LD (schema.org JobPosting), тот же приём что EventbriteScraper использует
    для событий. Тянем только для прошедших title pre-filter (экономия запросов,
    паттерн как в LinkedInScraper._enrich_descriptions).

Параметры поиска (без изменений):
  search=<keyword>   — fulltext поиск по названию/описанию
  countryCode=DK     — только датские позиции
  isRemote=true      — remote позиции
  limit=<n>          — кол-во результатов

Ключи в ответе v2:
  docs[]             — массив вакансий (не "jobs")
  id                 — используется и для url, и для source_id
  company.name       — название компании
  location.address   — адрес/город
  isRemote           — bool

Pre-filter по title через _is_tech_title() — не тратим токены на нерелевантные позиции.
"""

import json
import logging
import re

import requests

from src.agents.scout_agent import _is_tech_title
from src.database.repository import Vacancy
from src.scrapers.base_scraper import BaseScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://thehub.io/api/v2/jobs"
_TIMEOUT_SEC = 15
_LIMIT_PER_SEARCH = 50
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Порядок атрибутов на странице TheHub: data-hid идёт ДО type — не завязываемся
# на порядок, ищем любой ld+json блок и проверяем @type после json.loads()
# (так же надёжнее к разметке, как EventbriteScraper делает для событий).
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

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

        # Pre-filter по title — экономия токенов (cheap check before expensive LLM call).
        # Enrich только прошедших фильтр — тот же паттерн, что в LinkedInScraper
        # (get_job() костует запрос, нет смысла тянуть описание для нерелевантных).
        filtered = [v for v in vacancies if _is_tech_title(v.title)]
        self._enrich_descriptions(filtered)
        log.info(
            "TheHub: fetched %d vacancies, %d passed title filter",
            len(vacancies), len(filtered),
        )
        return filtered

    def _enrich_descriptions(self, vacancies: list[Vacancy]) -> None:
        """v2 API не отдаёт description в списке — берём с детальной страницы
        вакансии (JSON-LD JobPosting), как EventbriteScraper делает для событий."""
        for vacancy in vacancies:
            try:
                resp = requests.get(vacancy.url, headers=_HEADERS, timeout=_TIMEOUT_SEC)
                resp.raise_for_status()
            except Exception:
                log.debug("TheHub: failed to fetch detail page for %s", vacancy.url)
                continue

            for match in _JSON_LD_RE.finditer(resp.text):
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict) or data.get("@type") != "JobPosting":
                    continue
                description = (data.get("description") or "").strip()
                if description:
                    vacancy.description = description
                break

    def _to_vacancy(self, job: dict) -> Vacancy | None:
        job_id = job.get("id") or job.get("_id")
        title = (job.get("title") or "").strip()
        if not job_id or not title:
            return None
        # v2 не отдаёт absoluteJobUrl — строим сами (проверено по HTML листинга).
        url = f"https://thehub.io/jobs/{job_id}"

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

        # isRemote приходит как bool из API — используем напрямую, не ждём LLM
        work_format = "remote" if job.get("isRemote") else "unknown"

        return Vacancy(
            source_id=f"thehub_{job_id}",
            title=title,
            url=url,
            company=company,
            location=location,
            description="",  # заполнится в _enrich_descriptions() после title pre-filter
            platform="thehub",
            work_format=work_format,
        )
