"""
Event scraper: ищет tech-события через DuckDuckGo (SRP, OCP).

Не парсит конкретные сайты — это позволяет находить события на любых платформах
(Meetup, Eventbrite, сайты конференций, IDA и т.д.) без отдельного scraper на каждый.
EventScoutAgent затем фильтрует нерелевантное через LLM.

При появлении Meetup API / Eventbrite API — добавить отдельный scraper (OCP).
"""

import logging
from datetime import datetime, timezone

from ddgs import DDGS  # пакет переименован из duckduckgo_search → ddgs

log = logging.getLogger(__name__)

_MAX_RESULTS_PER_QUERY = 8
_SNIPPET_CHARS = 400

# Запросы нацелены на Aarhus и Данию. Год подставляется динамически,
# чтобы поиск не возвращал прошлогодние события.
_QUERY_TEMPLATES = [
    "tech meetup Aarhus {year}",
    "developer meetup Denmark {year}",
    "IT konference Denmark {year}",
    "software engineering conference Denmark {year}",
    "hackathon Aarhus {year}",
    "programming workshop Aarhus {year}",
    "tech networking event Aarhus {year}",
]


class EventScraper:
    """
    Не наследует BaseScraper — возвращает сырые search results, не Vacancy.
    BaseScraper предназначен для вакансий (OCP: не расширяем под другой контракт).
    """

    def fetch(self) -> list[dict[str, str]]:
        """
        Returns list of {"title": ..., "body": ..., "href": ...} from DuckDuckGo.
        EventScoutAgent принимает этот формат на вход.
        """
        year = datetime.now(timezone.utc).year
        queries = [t.format(year=year) for t in _QUERY_TEMPLATES]

        seen_urls: set[str] = set()
        results: list[dict[str, str]] = []

        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        hits = ddgs.text(query, max_results=_MAX_RESULTS_PER_QUERY)
                        for r in hits:
                            url = r.get("href", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                results.append({
                                    "title": r.get("title", ""),
                                    "body":  r.get("body", "")[:_SNIPPET_CHARS],
                                    "href":  url,
                                })
                    except Exception:
                        log.warning("EventScraper: query failed: '%s'", query)
                        continue
        except Exception:
            log.exception("EventScraper: DDGS session failed")

        log.info("EventScraper: %d unique results from %d queries", len(results), len(queries))
        return results
