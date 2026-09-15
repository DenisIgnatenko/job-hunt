"""
Outreach Scout Agent: извлекает и классифицирует людей из веб-поиска (SRP).

Тот же подход, что EventScoutAgent/EntertainmentScoutAgent:
  - На вход: сырые search results (title + body + url), один батч на всю компанию
  - Один LLM вызов на весь батч — дешевле per-item
  - LLM решает: реальный ли это человек в этой компании, какая у него роль
  - На выходе: только контакты с confidence >= порога
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.voice import extract_json_object
from src.database.repository import OutreachContact

log = logging.getLogger(__name__)

_SYSTEM = """
You are helping Denis Ignatenko, a backend software engineer job-hunting in Denmark,
identify real people at a specific company worth reaching out to about job opportunities
(open or unlisted).

You will receive a company name, followed by raw web search results (title + snippet +
url) that may contain LinkedIn profile pages of people who work or worked there.

Your task: identify results that are genuinely a LinkedIn profile of a real person who
plausibly currently works at THIS company, in a role that could plausibly speak to
open or unlisted engineering roles there — a tech lead / engineering manager / CTO /
head of engineering, or a recruiter / HR / talent acquisition / people team person.

Be strict. Search engines return a lot of noise for these queries: people at unrelated
companies, people who just have the company name somewhere in an old job history,
executives with no hiring signal, or search-engine junk with no real connection to the
company at all. If the snippet doesn't clearly show this person is currently at THIS
company in a relevant role, exclude them, even if the title looks superficially related.

Return a JSON object:
{
  "contacts": [
    {
      "full_name": "<their name>",
      "headline": "<their job title / headline, as shown>",
      "role_category": "<tech_lead|hiring_manager|hr|other>",
      "linkedin_url": "<the profile URL, exactly as given>",
      "confidence": <int 1-10, how confident this is a real, currently-relevant match>
    }
  ]
}

role_category guide:
- tech_lead: engineering/tech leadership — tech lead, engineering manager, CTO, VP
  Engineering, head of engineering/platform
- hiring_manager: manages the team that would own the role, but not purely technical
  (e.g. Head of Product, department director) — use only when tech_lead doesn't fit
- hr: recruiter, talent acquisition, people/HR team, in-house or agency
- other: clearly at the company, plausible but doesn't fit the above

Only include entries with confidence >= 6. If nothing qualifies, return {"contacts": []}.
Return ONLY the JSON object. No markdown.
""".strip()

_MAX_TOKENS = 1200
_MIN_CONFIDENCE = 6


@dataclass
class ScoredContact:
    contact: OutreachContact
    confidence: int


class OutreachScoutAgent(BaseAgent):
    def run(
        self, company: str, raw_results: list[dict[str, str]], vacancy_id: int, source: str
    ) -> list[ScoredContact]:
        """
        raw_results: [{"title": ..., "body": ..., "href": ...}, ...] — from
        OutreachFinder (either ddgs or LinkedIn search, already normalized).
        Returns only contacts with confidence >= _MIN_CONFIDENCE.
        """
        if not raw_results:
            return []

        prompt = self._build_prompt(company, raw_results)
        raw_response = self._chat(system=_SYSTEM, user=prompt, max_tokens=_MAX_TOKENS)

        try:
            data = json.loads(extract_json_object(raw_response))
        except json.JSONDecodeError:
            log.warning("OutreachScout: failed to parse LLM response: %s", raw_response[:200])
            return []

        scored: list[ScoredContact] = []
        for item in data.get("contacts", []):
            confidence = int(item.get("confidence") or 0)
            name = (item.get("full_name") or "").strip()
            relevant = confidence >= _MIN_CONFIDENCE

            log.info(
                "[%d/10] %s | %s (%s) — %s",
                confidence,
                "✅" if relevant else "❌",
                name,
                item.get("role_category", "?"),
                item.get("linkedin_url", ""),
            )

            if not relevant:
                continue

            contact = self._to_contact(item, company, vacancy_id, source)
            if contact:
                scored.append(ScoredContact(contact=contact, confidence=confidence))

        log.info(
            "OutreachScout done: %d relevant / %d found / %d search results for '%s'",
            len(scored), len(data.get("contacts", [])), len(raw_results), company,
        )
        return scored

    def _build_prompt(self, company: str, results: list[dict[str, str]]) -> str:
        lines = [f"Company: {company}\n", "Search results:\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")[:300]
            url = r.get("href", "")
            lines.append(f"[{i}] {title}\n{body}\n{url}\n")
        return "\n".join(lines)

    def _to_contact(
        self, item: dict[str, Any], company: str, vacancy_id: int, source: str
    ) -> OutreachContact | None:
        full_name = (item.get("full_name") or "").strip()
        linkedin_url = (item.get("linkedin_url") or "").strip()
        role_category = item.get("role_category") or "other"
        if role_category not in ("tech_lead", "hiring_manager", "hr", "other"):
            role_category = "other"
        if not full_name or not linkedin_url:
            return None
        return OutreachContact(
            vacancy_id=vacancy_id,
            company=company,
            full_name=full_name,
            headline=item.get("headline") or None,
            role_category=role_category,
            linkedin_url=linkedin_url,
            source=source,
        )
