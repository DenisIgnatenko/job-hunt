"""
Jobindex RSS scraper (SRP).
One request per keyword — OR logic via separate queries, deduplicated by source_id.
"""

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from src.config import config
from src.database.repository import Vacancy
from src.scrapers.base_scraper import BaseScraper

log = logging.getLogger(__name__)
_TIMEOUT_SEC = 15


class JobindexScraper(BaseScraper):
    def fetch(self) -> list[Vacancy]:
        seen: set[str] = set()
        vacancies: list[Vacancy] = []

        keywords = config.jobindex_keywords or ["softwareudvikler"]
        for keyword in keywords:
            url = self._build_url(keyword)
            try:
                response = requests.get(url, timeout=_TIMEOUT_SEC)
                response.raise_for_status()
            except Exception:
                log.exception("Jobindex: request failed for keyword '%s'", keyword)
                continue

            for vacancy in self._parse(response.text):
                if vacancy.source_id not in seen:
                    seen.add(vacancy.source_id)
                    vacancies.append(vacancy)

        log.info("Jobindex: fetched %d unique vacancies across %d keywords", len(vacancies), len(keywords))
        return vacancies

    def _build_url(self, keyword: str) -> str:
        base = config.jobindex_rss_url
        # URL-encode spaces as + for Jobindex query parameter
        q = keyword.strip().replace(" ", "+")
        url = f"{base}?q={q}"
        if config.jobindex_location:
            url += f"&jobtitle={config.jobindex_location}"
        return url

    def _parse(self, xml_text: str) -> list[Vacancy]:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return []

        vacancies = []
        for item in channel.findall("item"):
            title = _text(item, "title")
            link = _text(item, "link")
            if not title or not link:
                continue

            source_id = hashlib.sha1(link.encode()).hexdigest()[:16]
            parsed_title, company = _split_title_company(title)
            vacancies.append(Vacancy(
                source_id=source_id,
                title=parsed_title,
                url=link,
                company=company,
                description=_text(item, "description"),
                posted_at=_parse_date(_text(item, "pubDate")),
                platform="jobindex",
            ))

        return vacancies


def _split_title_company(raw: str) -> tuple[str, str | None]:
    """Split 'Job Title, Company Name A/S' into (title, company)."""
    if ", " in raw:
        idx = raw.rfind(", ")
        return raw[:idx].strip(), raw[idx + 2:].strip()
    return raw.strip(), None


def _text(element: ET.Element, tag: str) -> str | None:
    node = element.find(tag)
    return node.text.strip() if node is not None and node.text else None


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None
