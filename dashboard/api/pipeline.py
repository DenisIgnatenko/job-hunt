"""
Research + letter pipeline без зависимости от Telegram (SRP).
Используется из дашборда. Бот использует jobs.py (там добавляется Telegram notification).
"""

import logging

from ddgs import DDGS  # FIX: пакет переименован из duckduckgo_search; старый импорт
                        # ловил ModuleNotFoundError и молча ронял Company report

from src.agents.base_agent import BaseAgent
from src.agents.letter_agent import LetterAgent
from src.agents.outreach_agent import OutreachAgent
from src.agents.outreach_scout_agent import OutreachScoutAgent
from src.agents.research_agent import ResearchAgent
from src.config import config
from src.database.repository import (
    CoverLetterRepository,
    OutreachContact,
    OutreachContactRepository,
    VacancyRepository,
)
from src.scrapers.outreach_finder import OutreachFinder

log = logging.getLogger(__name__)

_vacancy_repo = VacancyRepository()
_letter_repo = CoverLetterRepository()
_researcher = ResearchAgent()
_letter_agent = LetterAgent()
_outreach_repo = OutreachContactRepository()
_outreach_finder = OutreachFinder()
_outreach_scout = OutreachScoutAgent()
_outreach_agent = OutreachAgent()


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


def regenerate_letter(vacancy_id: int, comments: str | None = None) -> str:
    """
    Blocking: пересоздаёт письмо без повторного research.
    Принимает опциональный фидбек пользователя и передаёт в LetterAgent.
    """
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")

    log.info("Regenerating letter for vacancy_id=%d, has_comments=%s", vacancy_id, bool(comments))
    letter = _letter_agent.run(vacancy, company=None, user_comments=comments)

    assert letter.id is not None, "Letter was not persisted"
    _vacancy_repo.update_status(vacancy_id, "letter_sent")
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
        return self._chat(system=_COMPANY_REPORT_SYSTEM, user=prompt, max_tokens=1400)

    def _search(self, company_name: str) -> str:
        queries = [
            f"{company_name} engineering culture tech stack",
            f"{company_name} company news 2025 2026",
            f"{company_name} glassdoor reviews employees",
        ]
        snippets: list[str] = []
        try:
            with DDGS(timeout=8) as ddgs:
                for q in queries:
                    try:
                        for r in ddgs.text(q, max_results=4):
                            body = r.get("body", "")[:300]
                            snippets.append(f"[{r.get('title','')}] {body}")
                    except Exception:
                        log.warning("Company report: query failed: '%s'", q)
                        continue
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
            max_tokens=1200,
        )


_company_report_agent = _CompanyReportAgent()
_match_agent = _MatchAnalysisAgent()


def generate_company_report(vacancy_id: int) -> str:
    """Blocking: web research + AI company dossier. Сохраняет в БД для кэша."""
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")
    company_name = vacancy.company or "Unknown company"
    log.info("Company report started: %s", company_name)
    report = _company_report_agent.run(company_name, vacancy.description or "")
    _vacancy_repo.save_company_report(vacancy_id, report)
    return report


def generate_match_analysis(vacancy_id: int) -> str:
    """Blocking: compares vacancy with Denis's resume. Сохраняет в БД для кэша."""
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")
    log.info("Match analysis started for vacancy_id=%d", vacancy_id)
    analysis = _match_agent.run(vacancy.title, vacancy.description or "")
    _vacancy_repo.save_match_analysis(vacancy_id, analysis)
    return analysis


# --- Outreach -----------------------------------------------------------

def find_outreach_contacts(vacancy_id: int) -> list[OutreachContact]:
    """
    Blocking: ищет людей в компании этой вакансии (ddgs, LinkedIn fallback),
    сохраняет найденных в БД. Дедуп по linkedin_url — повторный вызов не плодит
    дубликаты, просто возвращает актуальный список по вакансии.
    """
    vacancy = _vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {vacancy_id} not found")
    company_name = vacancy.company or "Unknown company"

    log.info("Outreach search started for vacancy_id=%d, company='%s'", vacancy_id, company_name)
    raw_results, source = _outreach_finder.find(company_name)
    scored = _outreach_scout.run(company_name, raw_results, vacancy_id, source)

    for sc in scored:
        contact_id, _is_new = _outreach_repo.upsert(sc.contact)
        sc.contact.id = contact_id

    log.info(
        "Outreach search done for vacancy_id=%d: %d contacts saved",
        vacancy_id, len(scored),
    )
    return _outreach_repo.get_by_vacancy(vacancy_id)


def draft_outreach_message(contact_id: int) -> str:
    """Blocking: генерирует LinkedIn connection-request note для контакта. Сохраняет в БД."""
    contact = _outreach_repo.get_by_id(contact_id)
    if not contact:
        raise ValueError(f"Outreach contact {contact_id} not found")
    vacancy = _vacancy_repo.get_by_id(contact.vacancy_id)
    if not vacancy:
        raise ValueError(f"Vacancy {contact.vacancy_id} not found")

    log.info("Drafting outreach message for contact_id=%d", contact_id)
    message = _outreach_agent.run(contact, vacancy)
    _outreach_repo.save_message_draft(contact_id, message)
    return message
