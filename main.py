"""
Entry point. Wires together the Telegram bot, APScheduler, and DB migrations.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.telegram_bot import build_app
from src.config import config
from src.database.schema import run_migrations
from src.scheduler.jobs import (
    job_scout_events,
    job_scout_jobindex,
    job_scout_linkedin,
    job_scout_remotive,
    job_scout_thehub,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    run_migrations()
    log.info("Database migrations applied")

    app = build_app()
    await app.initialize()

    # Все scrapers запускаются ночью по UTC, чтобы к 8:00 CEST (= 6:00 UTC)
    # подборка была готова. Расписание разнесено чтобы не нагружать API одновременно.
    #
    # UTC → CEST (лето, UTC+2):
    #   04:00 UTC = 06:00 CEST  Jobindex
    #   04:10 UTC = 06:10 CEST  Remotive
    #   04:20 UTC = 06:20 CEST  The Hub
    #   04:35 UTC = 06:35 CEST  LinkedIn  (медленный — куки, get_job())
    #   05:10 UTC = 07:10 CEST  Events    (Eventbrite + DuckDuckGo + LLM)
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        job_scout_jobindex,
        trigger=CronTrigger(hour=4, minute=0),
        args=[app],
        id="scout_jobindex",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_remotive,
        trigger=CronTrigger(hour=4, minute=10),
        args=[app],
        id="scout_remotive",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_thehub,
        trigger=CronTrigger(hour=4, minute=20),
        args=[app],
        id="scout_thehub",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_linkedin,
        trigger=CronTrigger(hour=4, minute=35),
        args=[app],
        id="scout_linkedin",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_events,
        trigger=CronTrigger(hour=5, minute=10),
        args=[app],
        id="scout_events",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started — daily at 04:00-05:10 UTC (06:00-07:10 CEST). "
        "Results ready by 08:00 local time."
    )

    if app.updater is None:
        raise RuntimeError("Application has no Updater — polling mode requires token-based setup")

    log.info("Starting Telegram bot polling")
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down")
    finally:
        scheduler.shutdown(wait=False)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
