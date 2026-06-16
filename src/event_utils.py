"""
Общая утилита для фильтрации событий по дате (DRY).
Используется и EventbriteScraper (структурированные данные), и EventScoutAgent
(LLM-извлечение из веб-поиска) — оба источника должны отсекать прошедшие события
одинаково, без дублирования логики.
"""

from datetime import date


def is_past_event_date(event_date: str | None, today: date) -> bool:
    """
    True, если event_date (формат YYYY-MM-DD) строго раньше today.
    Если дата неизвестна или не парсится — событие НЕ считается прошедшим
    (нет данных = не отклоняем, в отличие от location-фильтра, где
    "if in doubt — reject"; здесь будущее не доказано, но и прошлое тоже).
    """
    if not event_date:
        return False
    try:
        parsed = date.fromisoformat(event_date[:10])
    except ValueError:
        return False
    return parsed < today
