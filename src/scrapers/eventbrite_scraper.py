"""
Eventbrite scraper: tech события в Дании (SRP, OCP).
Парсит публичные страницы поиска — API ключ не нужен.
Eventbrite встраивает данные о событиях в HTML как JSON-LD (Schema.org Event),
что позволяет извлекать структурированные данные без JS-рендеринга.
"""

import json
import logging
import re
from datetime import datetime

import requests

from src.database.repository import CommunityEvent

log = logging.getLogger(__name__)

_TIMEOUT_SEC = 15
# Реальный User-Agent — без него Eventbrite возвращает 403
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Страницы поиска: Aarhus + вся Дания + remote
_SEARCH_URLS = [
    "https://www.eventbrite.com/d/denmark--aarhus/tech/",
    "https://www.eventbrite.com/d/denmark--aarhus/software/",
    "https://www.eventbrite.com/d/denmark/technology/",
    "https://www.eventbrite.com/d/denmark/developer/",
]

# Ключевые слова для pre-filter по названию события.
# Дешёвый фильтр до LLM — отсекает явно нерелевантное (курсы по юриспруденции,
# банковские тренинги, йога и т.д., которые Eventbrite выдаёт на запрос "tech").
_TECH_EVENT_KEYWORDS = {
    "software", "developer", "developer", "programming", "coding", "code",
    "python", "java", "javascript", "typescript", "golang", "rust", "kotlin",
    "backend", "frontend", "fullstack", "devops", "cloud", "kubernetes", "docker",
    "api", "microservices", "data", "machine learning", "ai ", "llm", "neural",
    "open source", "hackathon", "tech talk", "meetup", "tech meet",
    "agile", "scrum", "architecture", "platform", "engineering",
    "startup", "it ", "saas", "web dev", "app dev",
    # Датские
    "softwareudvikler", "udvikler", "programmering", "teknologi",
}

# JSON-LD паттерн: Eventbrite кладёт данные событий в <script type="application/ld+json">
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _is_tech_event(title: str) -> bool:
    """Pre-filter: возвращает True если название события содержит tech-ключевое слово."""
    lower = title.lower()
    return any(kw in lower for kw in _TECH_EVENT_KEYWORDS)


class EventbriteScraper:
    """
    Не наследует BaseScraper — возвращает CommunityEvent, не Vacancy.
    BaseScraper предназначен только для вакансий (OCP: не расширяем под другой контракт).
    """

    def fetch(self) -> list[CommunityEvent]:
        seen: set[str] = set()
        events: list[CommunityEvent] = []

        for url in _SEARCH_URLS:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT_SEC)
                resp.raise_for_status()
            except Exception:
                log.exception("Eventbrite: request failed for %s", url)
                continue

            for ev in self._parse_page(resp.text):
                if ev.url in seen:
                    continue
                seen.add(ev.url)
                relevant = _is_tech_event(ev.title)
                log.info(
                    "[%d/10] %s | %s — %s (%s)",
                    ev.score,
                    "✅" if relevant else "❌",
                    ev.title,
                    ev.location or "?",
                    ev.event_date or "date unknown",
                )
                if relevant:
                    events.append(ev)

        log.info("Eventbrite: fetched %d events total", len(events))
        return events

    def _parse_page(self, html: str) -> list[CommunityEvent]:
        events: list[CommunityEvent] = []
        for match in _JSON_LD_RE.finditer(html):
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            # Eventbrite кладёт события в ItemList.itemListElement[].item
            # (не напрямую как @type=Event на верхнем уровне)
            candidates = data if isinstance(data, list) else [data]
            for block in candidates:
                if not isinstance(block, dict):
                    continue
                if block.get("@type") == "ItemList":
                    for list_item in block.get("itemListElement", []):
                        item = list_item.get("item") if isinstance(list_item, dict) else None
                        if isinstance(item, dict) and item.get("@type") == "Event":
                            ev = self._to_event(item)
                            if ev:
                                events.append(ev)
                elif block.get("@type") == "Event":
                    # На случай если структура изменится
                    ev = self._to_event(block)
                    if ev:
                        events.append(ev)

        if not events:
            log.debug("Eventbrite: no JSON-LD Event objects found in page")
        return events

    def _to_event(self, data: dict) -> CommunityEvent | None:
        title = (data.get("name") or "").strip()
        url = (data.get("url") or "").strip()
        if not title or not url:
            return None

        location = _extract_location(data.get("location"))
        event_date = _parse_date(data.get("startDate"))

        organizer_raw = data.get("organizer")
        organizer: str | None = None
        if isinstance(organizer_raw, dict):
            organizer = organizer_raw.get("name") or None
        elif isinstance(organizer_raw, list) and organizer_raw:
            organizer = (organizer_raw[0] or {}).get("name") or None

        description = (data.get("description") or "")[:300] or None

        # Базовый скоринг: Aarhus = 8, остальная Дания = 6
        score = 8 if location and "aarhus" in location.lower() else 6

        return CommunityEvent(
            title=title,
            url=url,
            event_type="other",
            location=location,
            event_date=event_date,
            description=description,
            organizer=organizer,
            score=score,
            source="eventbrite",
        )


def _extract_location(raw: object) -> str | None:
    if not raw:
        return None
    if isinstance(raw, str):
        return raw or None
    if not isinstance(raw, dict):
        return None

    # Сначала пробуем вложенный address
    addr = raw.get("address")
    if isinstance(addr, dict):
        city = addr.get("addressLocality") or ""
        country = addr.get("addressCountry") or ""
        combined = ", ".join(p for p in [city, country] if p)
        if combined:
            return combined

    # Fallback: name поля location
    return raw.get("name") or None


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d")
    except ValueError:
        # Иногда дата уже в формате YYYY-MM-DD
        return value[:10] if len(value) >= 10 else None
