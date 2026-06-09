"""
Scout agent: scores and filters raw vacancies (SRP).
Decides which vacancies are worth showing to Denis.
"""

import json
import logging
import re

from dataclasses import dataclass

from src.agents.base_agent import BaseAgent
from src.database.repository import Vacancy, VacancyRepository

log = logging.getLogger(__name__)


@dataclass
class ScoredVacancy:
    vacancy: Vacancy
    score: int
    reason: str
    work_format: str   # remote | hybrid | onsite | unknown
    stack: str         # "Java, Spring Boot, Kafka" or "not specified"

# Denis: Java + Go + Node.js + TypeScript, based in Aarhus, Denmark
_SYSTEM = """
You are a job-hunt assistant for a backend software engineer.

Candidate profile:
- Skills: Java (Spring Boot), Go, Node.js, TypeScript, React
- Experience: 5+ years, backend and fullstack roles
- Location: Aarhus, Denmark
- Target roles: backend developer, software engineer, fullstack engineer, platform engineer
- NOT looking for: teaching, management without coding, DevOps-only, PHP-only, .NET-only

## Location rules — apply BEFORE scoring
These are hard filters. If a vacancy fails, set score=2, relevant=false immediately.

REJECT (score 2, relevant=false):
- Onsite or hybrid role located outside Denmark (Sweden, Germany, Netherlands, UK, US, etc.)
- Remote role explicitly restricted to US, North America, or a specific non-EU country
- "EMEA" role that is clearly a sales/business territory role (not a pure engineering remote role)

ACCEPT (proceed to skill scoring):
- Any role located in Denmark (Copenhagen, Aarhus, remote DK, etc.)
- Remote role open to EU / EMEA / Europe / worldwide with no geographic restriction
- Remote role with no location mentioned (assume worldwide)

## Skill scoring (apply only if location is accepted)
- 8-10: strong match — Java/Go/Node.js/TypeScript stack, correct seniority
- 5-7:  partial match — adjacent stack, or junior/senior mismatch
- 1-4:  wrong stack, wrong role type

Mark relevant=true if score >= 5 AND location was accepted.
Return ONLY a JSON object. No markdown, no extra text.
{
  "score": <int 1-10>,
  "reason": "<one sentence explaining the score and location decision>",
  "relevant": <true|false>,
  "work_format": "<remote|hybrid|onsite|unknown>",
  "stack": "<comma-separated tech mentioned, or 'not specified'>"
}
""".strip()


class ScoutAgent(BaseAgent):
    def __init__(self, repo: VacancyRepository | None = None) -> None:
        super().__init__()
        self._repo = repo or VacancyRepository()

    def run(self, vacancies: list[Vacancy]) -> list[ScoredVacancy]:
        """Pre-filter by title, then score survivors with LLM."""
        tech = [v for v in vacancies if _is_tech_title(v.title)]
        skipped = len(vacancies) - len(tech)
        if skipped:
            log.info("Pre-filter: skipped %d non-tech titles, scoring %d", skipped, len(tech))

        relevant = []
        for vacancy in tech:
            result = self._score(vacancy)
            if result.get("relevant"):
                relevant.append(ScoredVacancy(
                    vacancy=vacancy,
                    score=result.get("score", 0),
                    reason=result.get("reason", ""),
                    work_format=result.get("work_format", "unknown"),
                    stack=result.get("stack", "not specified"),
                ))
        return relevant

    def _score(self, vacancy: Vacancy) -> dict:
        prompt = (
            f"Title: {vacancy.title}\n"
            f"Company: {vacancy.company or 'unknown'}\n"
            f"Location: {vacancy.location or 'unknown'}\n"
            f"Description:\n{(vacancy.description or 'N/A')[:800]}"
        )
        raw = self._chat(system=_SYSTEM, user=prompt, max_tokens=128)
        try:
            result = json.loads(_strip_markdown(raw))
        except json.JSONDecodeError:
            log.warning("Scout: failed to parse response for '%s': %s", vacancy.title, raw)
            result = {"score": 0, "reason": "parse error", "relevant": False}

        log.info(
            "[%d/10] %s | %s — %s",
            result.get("score", 0),
            "✅" if result.get("relevant") else "❌",
            vacancy.title,
            result.get("reason", ""),
        )
        return result


_TECH_KEYWORDS = {
    # English
    "software", "developer", "engineer", "backend", "frontend", "fullstack",
    "full-stack", "full stack", "programmer", "architect", "devops",
    "java", "spring", "node", "nodejs", "typescript", "javascript",
    "python", "golang", "kotlin", "scala", "rust", "cloud", "api",
    "platform", "data engineer", "ml engineer", "tech lead",
    # Danish
    "udvikler", "softwareudvikler", "programmør", "systemudvikler",
    "webudvikler", "applikationsudvikler",
}


def _is_tech_title(title: str) -> bool:
    """Return True if the job title contains at least one tech keyword."""
    lower = title.lower()
    return any(kw in lower for kw in _TECH_KEYWORDS)


def _strip_markdown(text: str) -> str:
    """Remove ```json ... ``` wrapper that Claude sometimes adds despite instructions."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text
