"""
Remotive scraper: remote-only tech jobs (SRP, OCP - new source = new class).
Public REST API, no auth, no rate limiting issues.
All Remotive jobs are remote by definition → work_format="remote" unconditionally.
"""

import logging
import re
from datetime import datetime

import requests

from src.database.repository import Vacancy
from src.scrapers.base_scraper import BaseScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://remotive.com/api/remote-jobs"
_TIMEOUT_SEC = 15

# software-dev covers backend, fullstack, devops. One request per category.
_CATEGORIES = ["software-dev", "devops-sysadmin"]


class RemotiveScraper(BaseScraper):
    def fetch(self) -> list[Vacancy]:
        seen: set[str] = set()
        vacancies: list[Vacancy] = []

        for category in _CATEGORIES:
            try:
                resp = requests.get(
                    _BASE_URL,
                    params={"category": category, "limit": 50},
                    timeout=_TIMEOUT_SEC,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                log.exception("Remotive: request failed for category '%s'", category)
                continue

            for job in data.get("jobs", []):
                v = self._to_vacancy(job)
                if v and v.source_id not in seen:
                    seen.add(v.source_id)
                    vacancies.append(v)

        log.info("Remotive: fetched %d vacancies", len(vacancies))
        return vacancies

    def _to_vacancy(self, job: dict) -> Vacancy | None:
        job_id = job.get("id")
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()
        if not job_id or not title or not url:
            return None

        # Tags from Remotive ("java", "spring-boot", etc.) - pass as description context
        tags: list[str] = job.get("tags") or []
        description_raw = job.get("description") or ""
        description = _strip_html(description_raw)[:2000]

        # Append tags to description so ScoutAgent can see the stack even if description is sparse
        if tags:
            description += f"\n\nTags: {', '.join(tags[:10])}"

        return Vacancy(
            source_id=f"remotive_{job_id}",
            title=title,
            url=url,
            company=job.get("company_name") or None,
            # candidate_required_location: "Worldwide", "Europe", "US" etc.
            location=job.get("candidate_required_location") or "Remote",
            description=description,
            posted_at=_parse_date(job.get("publication_date")),
            platform="remotive",
            work_format="remote",  # Remotive is remote-only — no need to ask LLM
        )


def _strip_html(text: str) -> str:
    """Remove HTML tags so LLM gets clean text, not markup noise."""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # Collapse multiple whitespace into single spaces
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None
