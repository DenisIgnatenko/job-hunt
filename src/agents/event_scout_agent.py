"""
Event Scout Agent: извлекает и скорит tech-события из веб-поиска (SRP).

Подход:
  - На вход: список raw snippets из DuckDuckGo (title + body + url)
  - Один LLM вызов на весь батч — дешевле чем per-item как в ScoutAgent
  - LLM решает: что реальное событие, что нет; ставит score и reason
  - На выходе: list[CommunityEvent] — только события score >= 5
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from src.agents.base_agent import BaseAgent
from src.database.repository import CommunityEvent

log = logging.getLogger(__name__)

_SYSTEM = """
You are a networking assistant for Denis Ignatenko — a backend software engineer
living in Aarhus, Denmark. He wants to meet other tech people, expand his network,
learn new things, and potentially find job leads through community events.

You will receive search results (title + snippet + url) about tech events.

Your task:
1. Identify which results describe real, upcoming tech events (meetups, conferences,
   workshops, hackathons, tech talks, networking events). Ignore: past events, news
   articles about events, general community pages without a specific event.
2. For each real upcoming event, extract structured info and score its value for Denis.

Return a JSON object:
{
  "events": [
    {
      "title": "<event name>",
      "url": "<direct link to the event page>",
      "event_type": "<meetup|conference|workshop|hackathon|other>",
      "location": "<city or 'Online'>",
      "event_date": "<YYYY-MM-DD or null if unknown>",
      "organizer": "<organizer name or null>",
      "description": "<1-2 sentences: what it is and why relevant>",
      "score": <int 1-10>,
      "reason": "<one sentence on networking value for Denis>"
    }
  ]
}

Scoring guide:
- 8-10: local Aarhus tech meetup, or major Denmark tech conference. High networking density.
- 5-7: Denmark-wide event, or strong remote/online event with relevant community.
- 1-4: too general, too far, already past, or clearly not a networking opportunity.

Include ALL events you find (any score). If a result is not a real event at all (news article,
generic page, job listing, etc.) — skip it entirely. If no real events found, return {"events": []}.
Return ONLY the JSON object. No markdown.
""".strip()

_MAX_TOKENS = 1500


@dataclass
class ScoredEvent:
    event: CommunityEvent
    reason: str


class EventScoutAgent(BaseAgent):
    def run(self, raw_results: list[dict[str, str]]) -> list[ScoredEvent]:
        """
        raw_results: list of {"title": ..., "body": ..., "href": ...} from DuckDuckGo.
        Returns only relevant events (score >= 5).
        """
        if not raw_results:
            return []

        prompt = self._build_prompt(raw_results)
        raw_response = self._chat(system=_SYSTEM, user=prompt, max_tokens=_MAX_TOKENS)

        try:
            data = json.loads(_strip_markdown(raw_response))
        except json.JSONDecodeError:
            log.warning("EventScout: failed to parse LLM response: %s", raw_response[:200])
            return []

        scored: list[ScoredEvent] = []
        for item in data.get("events", []):
            score = int(item.get("score") or 0)
            title = (item.get("title") or "").strip()
            reason = item.get("reason", "")
            relevant = score >= 5

            # Логируем всё — как ScoutAgent — чтобы видеть причины отклонения
            log.info(
                "[%d/10] %s | %s — %s",
                score,
                "✅" if relevant else "❌",
                title,
                reason,
            )

            if not relevant:
                continue

            event = self._to_event(item)
            if event:
                scored.append(ScoredEvent(event=event, reason=reason))

        log.info(
            "EventScout done: %d relevant / %d found / %d search results",
            len(scored), len(data.get("events", [])), len(raw_results),
        )
        return scored

    def _build_prompt(self, results: list[dict[str, str]]) -> str:
        lines = ["Search results about tech events in Denmark/Aarhus:\n"]
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
        )


def _strip_markdown(text: str) -> str:
    """Remove ```json ... ``` wrapper that Claude sometimes adds."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text
