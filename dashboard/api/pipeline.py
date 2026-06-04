"""
Research + letter pipeline без зависимости от Telegram (SRP).
Используется из дашборда. Бот использует jobs.py (там добавляется Telegram notification).
"""

import logging

from duckduckgo_search import DDGS

from src.agents.base_agent import BaseAgent
from src.agents.letter_agent import LetterAgent
from src.agents.research_agent import ResearchAgent
from src.config import config
from src.database.repository import CoverLetterRepository, VacancyRepository

log = logging.getLogger(__name__)

_vacancy_repo = VacancyRepository()
_letter_repo = CoverLetterRepository()
_researcher = ResearchAgent()
_letter_agent = LetterAgent()


def run_research_pipeline(vacancy_id: int) -> str:
    """
    Blocking: research + letter generation.
    Возвращает текст сопроводительного письма.
    Вызывать через asyncio.to_thread() из async контекста.
    """
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")

    log.info("Dashboard pipeline started for vacancy_id=%d", vacancy_id)
    _vacancy_repo.update_status(vacancy_id, "in_progress")

    company = _researcher.run(vacancy)
    letter = _letter_agent.run(vacancy, company)

    assert letter.id is not None, "Letter was not persisted"
    _vacancy_repo.update_status(vacancy_id, "letter_sent")

    log.info("Dashboard pipeline done for vacancy_id=%d", vacancy_id)
    return letter.body


# --- Company Report ---------------------------------------------------------

_COMPANY_REPORT_SYSTEM = """
You are a recruitment intelligence analyst helping Denis Ignatenko evaluate a potential employer.
Denis is a backend engineer (Java, Spring Boot, Go, Node.js, TypeScript) based in Aarhus, Denmark.

Using the web search results, write a comprehensive company report. Use markdown formatting.

## Overview
What the company does. Product, market, customers. 2-3 specific sentences.

## Tech Stack & Engineering
Known technologies, architecture approach, engineering team size if known.
What it's actually like to work there as a developer.

## Company Stage & Health
Startup / scale-up / enterprise. Funding, growth signals, headcount trend.
Any red flags: layoffs, negative reviews, high turnover.

## Culture & Values
What they claim vs what employees actually say. Work-life balance signals.

## Recent News
Significant events in the last 6-12 months: funding, product launches, layoffs, leadership changes.

## Candidate Intelligence
Interview style if known. What they value in engineers. Salary signals.

## Verdict
🟢 Green flags | 🔴 Red flags
**Overall:** worth applying / consider carefully / avoid — one sentence with reason.

Be specific and honest. Avoid corporate clichés. If data is missing, say so. Max 450 words.
""".strip()


class _CompanyReportAgent(BaseAgent):
    def run(self, company_name: str, job_description: str) -> str:  # type: ignore[override]
        web = self._search(company_name)
        prompt = (
            f"Company: {company_name}\n\n"
            f"## Web search results\n{web}\n\n"
            f"## Job description (excerpt)\n{job_description[:800]}"
        )
        return self._chat(system=_COMPANY_REPORT_SYSTEM, user=prompt, max_tokens=900)

    def _search(self, company_name: str) -> str:
        queries = [
            f"{company_name} engineering culture tech stack",
            f"{company_name} company news 2025 2026",
            f"{company_name} glassdoor reviews employees",
        ]
        snippets: list[str] = []
        try:
            with DDGS() as ddgs:
                for q in queries:
                    for r in ddgs.text(q, max_results=4):
                        body = r.get("body", "")[:300]
                        snippets.append(f"[{r.get('title','')}] {body}")
        except Exception:
            log.warning("Company report: web search failed for '%s'", company_name)
        return "\n\n".join(snippets) if snippets else "No web results found."


# --- Match Analysis ---------------------------------------------------------

_MATCH_SYSTEM = """
You are a career coach giving Denis Ignatenko an honest assessment of a job opportunity.
Denis's resume is provided. Analyze how well he fits the vacancy.

Use markdown formatting:

## Match Score: X/10

## ✅ Strong matches
Skills and experience that directly satisfy the requirements.

## ⚠️ Partial matches / gaps
Areas where Denis partially fits or needs to demonstrate more.

## ❌ Missing
Required skills or experience Denis doesn't have.

## 💬 Honest assessment
2-3 sentences: how strong is Denis as a candidate? Be direct — false encouragement wastes time.

## 🎯 Application strategy
What to emphasize in cover letter and interview. Specific angles that give Denis an edge.

Do not sugarcoat. Denis needs accurate information to decide whether to apply.
""".strip()


class _MatchAnalysisAgent(BaseAgent):
    def run(self, job_title: str, job_description: str) -> str:  # type: ignore[override]
        prompt = (
            f"## Job Title\n{job_title}\n\n"
            f"## Job Description\n{job_description[:2000]}\n\n"
            f"## Denis's Resume\n{config.resume_text[:3000]}"
        )
        return self._chat(
            system=self._system_with_resume(_MATCH_SYSTEM),
            user=prompt,
            max_tokens=800,
        )


_company_report_agent = _CompanyReportAgent()
_match_agent = _MatchAnalysisAgent()


def generate_company_report(vacancy_id: int) -> str:
    """Blocking: web research + AI company dossier for candidate decision-making."""
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")
    company_name = vacancy.company or "Unknown company"
    log.info("Company report started: %s", company_name)
    return _company_report_agent.run(company_name, vacancy.description or "")


def generate_match_analysis(vacancy_id: int) -> str:
    """Blocking: compares vacancy with Denis's resume, returns honest fit assessment."""
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")
    log.info("Match analysis started for vacancy_id=%d", vacancy_id)
    return _match_agent.run(vacancy.title, vacancy.description or "")
