"""
LinkedIn job scraper (SRP).
Moderate use: one session per process, 2 searches, random delays.
After initial search, fetches full description for each candidate — otherwise
Claude scores blindly on title only and passes irrelevant jobs at 5/10.
"""

import logging
import random
import time

import requests as req_lib
from linkedin_api import Linkedin

from src.agents.scout_agent import _is_tech_title
from src.config import config
from src.database.repository import Vacancy
from src.scrapers.base_scraper import BaseScraper

log = logging.getLogger(__name__)

_LISTED_WITHIN_SEC = 12 * 3600
_LIMIT_PER_SEARCH = 20
_DELAY_BETWEEN_SEARCHES = (5, 12)
_DELAY_BETWEEN_DETAIL_FETCHES = (2, 5)

_SEARCHES = [
    {
        "keywords": "Backend Developer Java Go Node.js TypeScript Spring Boot",
        "location_name": "Denmark",
        "listed_at": _LISTED_WITHIN_SEC,
        "limit": _LIMIT_PER_SEARCH,
    },
    {
        "keywords": "Backend Software Engineer Remote Denmark Java Go Node.js",
        "location_name": "Denmark",
        "listed_at": _LISTED_WITHIN_SEC,
        "limit": _LIMIT_PER_SEARCH,
    },
]


class LinkedInScraper(BaseScraper):
    _session: Linkedin | None = None

    def _get_session(self) -> Linkedin:
        if LinkedInScraper._session is None:
            log.info("LinkedIn: initialising session")
            if config.linkedin_cookie and config.linkedin_jsessionid:
                jar = req_lib.cookies.RequestsCookieJar()
                jar.set("li_at", config.linkedin_cookie,
                        domain=".linkedin.com", path="/")
                jar.set("JSESSIONID", config.linkedin_jsessionid,
                        domain=".linkedin.com", path="/")
                LinkedInScraper._session = Linkedin("", "", cookies=jar)
            else:
                LinkedInScraper._session = Linkedin(
                    config.linkedin_email, config.linkedin_password
                )
        return LinkedInScraper._session

    def fetch(self) -> list[Vacancy]:
        try:
            api = self._get_session()
        except Exception:
            log.exception("LinkedIn: login failed")
            return []

        seen: set[str] = set()
        vacancies: list[Vacancy] = []

        for i, search_params in enumerate(_SEARCHES):
            if i > 0:
                time.sleep(random.uniform(*_DELAY_BETWEEN_SEARCHES))
            try:
                results = api.search_jobs(**search_params)
            except Exception:
                log.exception("LinkedIn: search failed for params %s", search_params)
                LinkedInScraper._session = None
                break

            for job in results:
                vacancy = self._to_vacancy(job)
                if vacancy and vacancy.source_id not in seen:
                    seen.add(vacancy.source_id)
                    vacancies.append(vacancy)

        # Enrich only title-filtered candidates — not all 25+ raw results.
        # get_job() costs an API call each; no point fetching for non-tech vacancies
        # that Scout will discard anyway.
        candidates = [v for v in vacancies if _is_tech_title(v.title)]
        self._enrich_descriptions(api, candidates)
        log.info(
            "LinkedIn: fetched %d vacancies, enriched %d with descriptions",
            len(vacancies), len(candidates),
        )
        return vacancies

    def _enrich_descriptions(self, api: Linkedin, vacancies: list[Vacancy]) -> None:
        """Fetch full job detail (description, company, location) for title-filtered candidates."""
        for i, vacancy in enumerate(vacancies):
            if i > 0:
                time.sleep(random.uniform(*_DELAY_BETWEEN_DETAIL_FETCHES))
            job_id = vacancy.source_id.removeprefix("li_")
            try:
                detail = api.get_job(job_id)

                description = detail.get("description", {}).get("text", "").strip()
                if description:
                    vacancy.description = description

                if not vacancy.location:
                    vacancy.location = detail.get("formattedLocation") or None

                if not vacancy.company:
                    vacancy.company = _extract_company_from_detail(detail) or None

            except Exception:
                log.debug("LinkedIn: failed to fetch detail for %s", job_id)

    def _to_vacancy(self, job: dict) -> Vacancy | None:
        job_id = self._extract_id(job.get("entityUrn", ""))
        if not job_id:
            return None
        title = job.get("title", "").strip()
        if not title:
            return None
        return Vacancy(
            source_id=f"li_{job_id}",
            title=title,
            url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            company=self._extract_company(job) or None,
            location=job.get("formattedLocation") or None,
            platform="linkedin",
        )

    @staticmethod
    def _extract_id(urn: str) -> str | None:
        parts = urn.split(":")
        return parts[-1] if len(parts) >= 4 else None

    @staticmethod
    def _extract_company(job: dict) -> str:
        try:
            details = job.get("companyDetails", {})
            for inner in details.values():
                if isinstance(inner, dict):
                    name = inner.get("companyResolutionResult", {}).get("name", "")
                    if name:
                        return name
        except Exception:
            pass
        return ""


def _extract_company_from_detail(detail: dict) -> str:
    """Extract company name from get_job() response (different structure than search_jobs)."""
    try:
        details = detail.get("companyDetails", {})
        for inner in details.values():
            if isinstance(inner, dict):
                result = inner.get("companyResolutionResult", {})
                name = result.get("name", "")
                if name:
                    return name
    except Exception:
        pass
    return ""
