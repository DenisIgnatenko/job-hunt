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

# Denis: Java + TypeScript/Node.js + Python + AI/LLM (RAG, agents), based in Aarhus, Denmark.
# Kept in sync with resume.md's "Job Search Preferences" section by hand — resume.md itself
# is never read by this agent (SRP: resume.md is candidate facts for letters/research; this
# prompt is scoring policy). Update both when Denis's targeting criteria change.
_SYSTEM = """
You are a job-hunt assistant for a backend/fullstack engineer.

Candidate profile:
- Skills: Java (Spring Boot), TypeScript, Node.js, Python; AI/LLM engineering (RAG pipelines,
  embeddings, vector search, AI agents, MCP servers); event-driven architecture, Kafka;
  DDD, Clean Architecture, Hexagonal/Ports and Adapters
- Experience: mid-level — comfortable with roles targeting roughly 2-5 years, not entry-level
  (0-1 years) and not Staff/Principal-level (8+ years) postings
- Location: Aarhus, Denmark
- Target roles: backend developer, software engineer, fullstack engineer, platform engineer,
  AI/LLM engineer. Permanent AND contract/freelance/fixed-term engagements are both welcome —
  do not penalize a posting for being a contract, consulting, or fixed-term role.
- NOT looking for: teaching, management without coding, DevOps-only / pure infrastructure roles

## Location rules — apply BEFORE scoring
These are hard filters. If a vacancy fails, set score=2, relevant=false immediately.

REJECT (score 2, relevant=false):
- Onsite or hybrid role located outside Denmark
- Remote role restricted to a specific region: EU, European Union, Europe, EMEA, UK, US, North America, Asia, etc.
  (Denmark is technically inside an "EU remote" scope, but Denis has explicitly said he does not
  want these — a company hiring broadly across the EU rather than for Denmark specifically is
  usually not building local roots there, often runs on contractor arrangements that skip Danish
  employment protections, and does nothing for the Danish-market career he's building. Reject it
  the same as any other region-restricted remote posting.)
- Any role where the location clearly excludes Denmark or is tied to a non-Danish office
- Requires a security clearance Denis cannot obtain

ACCEPT (proceed to skill scoring):
- Any role located anywhere in Denmark, any format — onsite, hybrid, or remote (Aarhus,
  Copenhagen, or any other Danish city)
- Remote role with no geographic restriction at all (worldwide, global, or location not mentioned)

If in doubt — reject. Denis only wants Danish-based roles (any city, any format) or truly
unrestricted worldwide remote.

## Skill scoring (apply only if location is accepted)
- 8-10: strong match — Java/TypeScript/Node.js/Python/AI-LLM stack, correct seniority bracket
- 5-7:  partial match — adjacent stack, or seniority bracket mismatch
- 1-4:  wrong stack, wrong role type

Score down (don't hard-reject) for:
- Requires native or fluent Danish (Denis is at A1, actively studying)
- Primarily C#, PHP, Go, or Ruby as the main stack, with no production experience elsewhere
- Mainframe, COBOL, DB2, or SOAP as a core requirement

Work out the location decision and stack match BEFORE writing any field below — the fields
are ordered "reason" first specifically so you reason to a conclusion, then report it, rather
than committing to a score before you've finished thinking. Do not think out loud or
re-evaluate inside the "reason" field itself — it should state only your final conclusion, in
one sentence, and "score"/"relevant" must be consistent with what "reason" says.
Return ONLY a JSON object. No markdown, no extra text.
{
  "reason": "<one final sentence explaining the score and location decision>",
  "score": <int 1-10>,
  "relevant": <true|false>,
  "work_format": "<remote|hybrid|onsite|unknown>",
  "stack": "<comma-separated tech mentioned, or 'not specified'>"
}

Mark relevant=true if score >= 5 AND location was accepted.
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
        # FIX: bumped from 128 — the expanded location/skill rules (EU-remote reasoning,
        # freelance carve-out) made the model write longer "reason" strings, which hit the
        # old ceiling mid-JSON and produced unparseable output (silently dropped a valid
        # Danish AI vacancy during testing). Give real headroom instead of only trusting
        # "one sentence" in the prompt to hold.
        raw = self._chat(system=_SYSTEM, user=prompt, max_tokens=256)
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
