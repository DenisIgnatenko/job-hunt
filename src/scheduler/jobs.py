"""
APScheduler job definitions (SRP: schedule wiring lives here).

HITL flow:
  job_scout()                  — scrape → score → notify Denis (В работу / Skip)
  Denis clicks "В работу"      → Telegram callback → run_research_for_vacancy()
  Denis clicks "Skip"          → vacancy marked 'rejected'
  run_research_for_vacancy()   — research + letter → notify Denis (plain text)
  Denis edits letter manually, applies, then: /applied <id>

IMPORTANT: all scraper/agent calls are blocking (requests, sqlite).
They run in a thread pool via asyncio.to_thread() so they never block the
event loop — Telegram polling stays alive during long LinkedIn fetches.
"""

import asyncio
import logging

from telegram.ext import Application

from src.agents.event_scout_agent import EventScoutAgent, ScoredEvent
from src.agents.letter_agent import LetterAgent
from src.agents.research_agent import ResearchAgent
from src.agents.scout_agent import ScoutAgent
from src.bot.telegram_bot import notify_event, notify_letter, notify_vacancy
from src.database.repository import CommunityEvent, CommunityEventRepository, VacancyRepository
from src.scrapers.event_scraper import EventScraper
from src.scrapers.eventbrite_scraper import EventbriteScraper
from src.scrapers.jobindex_scraper import JobindexScraper
from src.scrapers.linkedin_scraper import LinkedInScraper
from src.scrapers.remotive_scraper import RemotiveScraper
from src.scrapers.thehub_scraper import TheHubScraper

log = logging.getLogger(__name__)

_vacancy_repo = VacancyRepository()
_event_repo = CommunityEventRepository()
_jobindex_scraper = JobindexScraper()
_linkedin_scraper = LinkedInScraper()
_remotive_scraper = RemotiveScraper()
_thehub_scraper = TheHubScraper()
_event_scraper = EventScraper()
_eventbrite_scraper = EventbriteScraper()
_scout = ScoutAgent(repo=_vacancy_repo)
_event_scout = EventScoutAgent()
_researcher = ResearchAgent()
_letter_agent = LetterAgent()


async def _run_scout(app: Application, scraper_name: str, raw: list) -> None:
    """Score and notify. DRY — shared by all scout jobs.
    Scoring is CPU+network bound — run in thread so event loop stays responsive.
    """
    scored = await asyncio.to_thread(_scout.run, raw)
    new_count = 0
    for sv in scored:
        sv.vacancy.work_format = sv.work_format  # persist Scout's assessment
        vacancy_id, is_new = _vacancy_repo.upsert(sv.vacancy)
        sv.vacancy.id = vacancy_id
        if not is_new:
            continue
        new_count += 1
        await notify_vacancy(
            app,
            vacancy_id=vacancy_id,
            title=sv.vacancy.title,
            company=sv.vacancy.company or "",
            location=sv.vacancy.location or "",
            url=sv.vacancy.url,
            score=sv.score,
            work_format=sv.work_format,
            stack=sv.stack,
            reason=sv.reason,
        )
    log.info(
        "%s scout done: %d new / %d relevant / %d fetched",
        scraper_name, new_count, len(scored), len(raw),
    )


async def job_scout_jobindex(app: Application) -> None:
    """Jobindex: scheduled every 6h."""
    log.info("Jobindex scout started")
    try:
        raw = await asyncio.to_thread(_jobindex_scraper.fetch)
        await _run_scout(app, "Jobindex", raw)
    except Exception:
        log.exception("Jobindex scout failed")


async def job_scout_linkedin(app: Application) -> None:
    """LinkedIn: scheduled every 12h."""
    log.info("LinkedIn scout started")
    try:
        raw = await asyncio.to_thread(_linkedin_scraper.fetch)
        await _run_scout(app, "LinkedIn", raw)
    except Exception:
        log.exception("LinkedIn scout failed")


async def job_scout_remotive(app: Application) -> None:
    """Remotive: remote-only jobs, scheduled every 6h (same as Jobindex)."""
    log.info("Remotive scout started")
    try:
        raw = await asyncio.to_thread(_remotive_scraper.fetch)
        await _run_scout(app, "Remotive", raw)
    except Exception:
        log.exception("Remotive scout failed")


async def job_scout_thehub(app: Application) -> None:
    """The Hub: главный датский tech job board, scheduled every 6h."""
    log.info("TheHub scout started")
    try:
        raw = await asyncio.to_thread(_thehub_scraper.fetch)
        await _run_scout(app, "TheHub", raw)
    except Exception:
        log.exception("TheHub scout failed")


async def _notify_new_events(
    app: Application, scored: list[ScoredEvent], source: str
) -> int:
    """DRY: upsert + notify для списка ScoredEvent. Возвращает кол-во новых."""
    new_count = 0
    for se in scored:
        event_id, is_new = _event_repo.upsert(se.event)
        se.event.id = event_id
        if not is_new:
            continue
        new_count += 1
        await notify_event(
            app,
            event_id=event_id,
            title=se.event.title,
            event_type=se.event.event_type,
            location=se.event.location or "",
            event_date=se.event.event_date or "",
            organizer=se.event.organizer or "",
            description=se.event.description or "",
            url=se.event.url,
            score=se.event.score,
        )
    log.info("%s: %d new events notified", source, new_count)
    return new_count


async def job_scout_events(app: Application) -> None:
    """
    Events: два источника параллельно.
    - DuckDuckGo → LLM извлечение/скоринг (широкий поиск)
    - Eventbrite → HTML парсинг JSON-LD (структурированные данные)
    Scheduled daily.
    """
    log.info("Events scout started")
    total_new = 0
    try:
        # --- Eventbrite: структурированные данные, без LLM ---
        eventbrite_events: list[CommunityEvent] = await asyncio.to_thread(
            _eventbrite_scraper.fetch
        )
        # Оборачиваем в ScoredEvent чтобы использовать общий helper
        eb_scored = [ScoredEvent(event=ev, reason=f"Eventbrite tech event") for ev in eventbrite_events]
        total_new += await _notify_new_events(app, eb_scored, "Eventbrite")

        # --- DuckDuckGo → LLM: широкий поиск по всему вебу ---
        raw = await asyncio.to_thread(_event_scraper.fetch)
        web_scored = await asyncio.to_thread(_event_scout.run, raw)
        total_new += await _notify_new_events(app, web_scored, "WebSearch")

        log.info("Events scout done: %d new total", total_new)
    except Exception:
        log.exception("Events scout failed")


async def run_research_for_vacancy(app: Application, vacancy_id: int) -> None:
    """
    Triggered by Denis clicking "В работу".
    Research + letter generation are blocking — run in thread.
    """
    log.info("Research pipeline started for vacancy_id=%d", vacancy_id)
    vacancy = _vacancy_repo.get_by_id(vacancy_id)

    if not vacancy:
        log.error("Vacancy %d not found", vacancy_id)
        return

    try:
        company = await asyncio.to_thread(_researcher.run, vacancy)
        letter = await asyncio.to_thread(_letter_agent.run, vacancy, company)
        assert letter.id is not None, "Letter was not persisted — DB insert failed"

        _vacancy_repo.update_status(vacancy_id, "letter_sent")

        await notify_letter(
            app,
            vacancy_id=vacancy_id,
            vacancy_title=vacancy.title,
            company=vacancy.company or "",
            apply_url=vacancy.url,
            body=letter.body,
        )
        log.info("Research pipeline complete for vacancy_id=%d", vacancy_id)

    except Exception:
        _vacancy_repo.update_status(vacancy_id, "new")
        log.exception("Research pipeline failed for vacancy_id=%d", vacancy_id)
