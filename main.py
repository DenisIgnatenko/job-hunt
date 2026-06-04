"""
Entry point. Wires together the Telegram bot, APScheduler, and DB migrations.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

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

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job_scout_jobindex,
        trigger="interval",
        hours=config.scout_interval_hours,
        args=[app],
        id="scout_jobindex",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_linkedin,
        trigger="interval",
        hours=config.linkedin_interval_hours,
        args=[app],
        id="scout_linkedin",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_remotive,
        trigger="interval",
        hours=config.scout_interval_hours,
        args=[app],
        id="scout_remotive",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_thehub,
        trigger="interval",
        hours=config.scout_interval_hours,
        args=[app],
        id="scout_thehub",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scout_events,
        trigger="interval",
        hours=24,
        args=[app],
        id="scout_events",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started (Jobindex/Remotive/TheHub every %dh, LinkedIn every %dh, Events daily)",
        config.scout_interval_hours,
        config.linkedin_interval_hours,
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
