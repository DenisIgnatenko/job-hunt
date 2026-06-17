"""
Entertainment scraper: ищет развлекательные события в Орхусе и Ютландии через DuckDuckGo (SRP, OCP).

Отличие от EventScraper (профессиональные tech-события):
- Другие поисковые запросы: концерты, фестивали, уличные выступления, театр
- Результаты передаются в EntertainmentScoutAgent (другой LLM-промпт)
- category='entertainment' у всех созданных CommunityEvent

OCP: новый класс — EventScraper не изменяется.
"""

import logging
from datetime import datetime, timezone

from duckduckgo_search import DDGS

log = logging.getLogger(__name__)

_MAX_RESULTS_PER_QUERY = 8
_SNIPPET_CHARS = 400

# Запросы нацелены на Орхус и восточную Ютландию.
# Месяц и год подставляются динамически — иначе DDG возвращает устаревшие анонсы.
_QUERY_TEMPLATES = [
    "concert live music Aarhus {month} {year}",
    "festival Aarhus {year}",
    "events Aarhus {month} {year}",
    "outdoor street performance Aarhus {year}",
    "teater forestilling Aarhus {month} {year}",
    "Aarhus Festuge {year}",
    "entertainment Jutland {month} {year}",
    "musik festival Østjylland {year}",
]


class EntertainmentScraper:
    """
    Не наследует BaseScraper — возвращает сырые search results, не Vacancy.
    BaseScraper предназначен только для вакансий (OCP).
    Аналог EventScraper но для досуговых событий.
    """

    def fetch(self) -> list[dict[str, str]]:
        """
        Returns list of {"title": ..., "body": ..., "href": ...} from DuckDuckGo.
        EntertainmentScoutAgent принимает этот формат на вход.
        """
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.strftime("%B")  # e.g. "June" — помогает DDG вернуть текущие события
        queries = [t.format(year=year, month=month) for t in _QUERY_TEMPLATES]

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
                        log.warning("EntertainmentScraper: query failed: '%s'", query)
                        continue
        except Exception:
            log.exception("EntertainmentScraper: DDGS session failed")

        log.info(
            "EntertainmentScraper: %d unique results from %d queries",
            len(results), len(queries),
        )
        return results
