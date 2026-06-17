"""
Entertainment Scout Agent: скорит развлекательные события в Орхусе и Ютландии (SRP, OCP).

Отличие от EventScoutAgent (tech-события):
- Другой system prompt: фокус на досуг, а не networking/tech
- Другие event_type: concert | festival | theater | outdoor | sport | market | other
- category='entertainment' у всех возвращаемых CommunityEvent
- Те же паттерны: batch LLM, is_past_event_date фильтр, логирование

OCP: EventScoutAgent не изменяется.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.event_scout_agent import ScoredEvent  # DRY: переиспользуем dataclass
from src.database.repository import CommunityEvent
from src.event_utils import is_past_event_date

log = logging.getLogger(__name__)

_SYSTEM = """
You are a lifestyle assistant for Denis Ignatenko, a software engineer living in Aarhus, Denmark.
He wants to discover cultural and entertainment events in Aarhus city and the surrounding
eastern Jutland area (Jutland peninsula, eastern coast).

Types of events Denis enjoys:
- Live music: concerts, rock, jazz, indie, classical, folk
- Outdoor festivals and street performances
- Food and cultural festivals
- Comedy shows and stand-up
- Theater and dance performances
- Art exhibitions with opening events or live elements
- Markets and fairs with entertainment
- Unique local experiences

Geographic scope (strict):
- Primary: Aarhus city and its suburbs — score 7-10
- Secondary: eastern Jutland within ~80 km of Aarhus (Horsens, Silkeborg, Skanderborg,
  Randers, Vejle, Grenaa) — score 5-6
- REJECT: Copenhagen/Zealand, Funen, western Jutland, online-only events

You will receive today's date, followed by search results (title + snippet + url).

Your task:
1. Identify real, upcoming or currently ongoing entertainment events.
   Ignore: past events (compare date against today's date provided), news articles
   about events, ticket aggregator home pages without a specific event, sport
   league schedules (generic), job listings, general "what's on" list pages
   without a specific event name.
2. For each real upcoming event, extract structured info and score it.

Return a JSON object:
{
  "events": [
    {
      "title": "<specific event name>",
      "url": "<direct link to event page>",
      "event_type": "<concert|festival|theater|outdoor|sport|market|other>",
      "location": "<city or venue, Aarhus if in Aarhus>",
      "event_date": "<YYYY-MM-DD or null if unknown>",
      "organizer": "<venue/organizer name or null>",
      "description": "<1-2 sentences: what it is, who performs, why interesting>",
      "score": <int 1-10>,
      "reason": "<one sentence on why Denis would enjoy this>"
    }
  ]
}

Scoring guide:
- 8-10: Aarhus city event Denis would clearly enjoy — known artist, popular festival,
        interesting outdoor or cultural event
- 5-7: good event slightly outside Aarhus (eastern Jutland), or smaller local event
- 1-4: wrong region, wrong type, or unclear if it is a real event

Include ALL identified events regardless of score.
If no real events found, return {"events": []}.
Return ONLY the JSON object. No markdown.
""".strip()

_MAX_TOKENS = 1500


class EntertainmentScoutAgent(BaseAgent):
    def run(self, raw_results: list[dict[str, str]]) -> list[ScoredEvent]:
        """
        raw_results: list of {"title": ..., "body": ..., "href": ...} from DuckDuckGo.
        Returns only relevant events (score >= 5) with category='entertainment'.
        """
        if not raw_results:
            return []

        today = date.today()
        prompt = self._build_prompt(raw_results, today)
        raw_response = self._chat(system=_SYSTEM, user=prompt, max_tokens=_MAX_TOKENS)

        try:
            data = json.loads(_strip_markdown(raw_response))
        except json.JSONDecodeError:
            log.warning("EntertainmentScout: failed to parse LLM response: %s", raw_response[:200])
            return []

        scored: list[ScoredEvent] = []
        for item in data.get("events", []):
            score = int(item.get("score") or 0)
            title = (item.get("title") or "").strip()
            reason = item.get("reason", "")
            event_date = (item.get("event_date") or "").strip() or None

            # Жёсткий фильтр по дате — LLM может ошибиться (DIP на is_past_event_date).
            is_past = is_past_event_date(event_date, today)
            relevant = score >= 5 and not is_past

            log.info(
                "[%d/10] %s | %s — %s%s",
                score,
                "✅" if relevant else "❌",
                title,
                reason,
                " [PAST]" if is_past else "",
            )

            if not relevant:
                continue

            event = self._to_event(item)
            if event:
                scored.append(ScoredEvent(event=event, reason=reason))

        log.info(
            "EntertainmentScout done: %d relevant / %d found / %d search results",
            len(scored), len(data.get("events", [])), len(raw_results),
        )
        return scored

    def _build_prompt(self, results: list[dict[str, str]], today: date) -> str:
        lines = [
            f"Today's date is {today.isoformat()}.",
            "Search results about entertainment events in Aarhus/Jutland:\n",
        ]
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")[:300]
            url = r.get("href", "")
            lines.append(f"[{i}] {title}\n{body}\n{url}\n")
        return "\n".join(lines)

    def _to_event(self, item: dict[str, Any]) -> CommunityEvent | None:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        score = int(item.get("score") or 0)
        if not title or not url or score < 5:
            return None
        return CommunityEvent(
            title=title,
            url=url,
            event_type=item.get("event_type") or "other",
            location=item.get("location") or None,
            event_date=item.get("event_date") or None,
            description=item.get("description") or None,
            organizer=item.get("organizer") or None,
            score=score,
            source="web",
            category="entertainment",  # ключевое отличие от professional-событий
        )


def _strip_markdown(text: str) -> str:
    """Remove ```json ... ``` wrapper that Claude sometimes adds."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text
