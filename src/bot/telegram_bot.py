"""
Telegram bot — all HITL interaction (SRP).

Flow:
  1. notify_vacancy()        — vacancy card with "В работу" / "Skip" buttons
  2. handle_callback "take"  — mark in_progress, trigger research pipeline
  3. notify_letter()         — cover letter text, Denis edits manually
  4. /applied <id>           — Denis marks vacancy as submitted
  5. /pending                — list unreviewed vacancies with buttons
  6. /done                   — list vacancies in pipeline
  7. /status                 — counts by stage
"""

import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from src.config import config
from src.database.repository import CommunityEventRepository, VacancyRepository

log = logging.getLogger(__name__)

_vacancy_repo = VacancyRepository()
_event_repo = CommunityEventRepository()

_FORMAT_EMOJI = {"remote": "🌐", "hybrid": "🔀", "onsite": "🏢", "unknown": "📍"}
_STATUS_EMOJI = {
    "new": "🔍", "in_progress": "⚙️", "letter_sent": "✉️",
    "applied": "📤", "interview": "🎙️", "offer": "🎉",
    "rejected": "❌", "rejected_by_company": "💔",
}
_EVENT_TYPE_EMOJI = {
    "meetup": "👥", "conference": "🎤", "workshop": "🛠️",
    "hackathon": "💻", "other": "📅",
}


def _e(text: str) -> str:
    """Escape HTML special characters in dynamic content."""
    return html.escape(text)


# --- Notification helpers ------------------------------------------------

async def notify_vacancy(
    app: Application,
    vacancy_id: int,
    title: str,
    company: str,
    location: str,
    url: str,
    score: int = 0,
    work_format: str = "unknown",
    stack: str = "",
    reason: str = "",
) -> None:
    lines = [f"🔍 <b>Новая вакансия</b> — {score}/10\n"]
    lines.append(f"<b>{_e(title)}</b>")
    if company:
        lines.append(f"🏢 {_e(company)}")
    if location:
        lines.append(f"📌 {_e(location)}")
    if work_format and work_format != "unknown":
        fmt_emoji = _FORMAT_EMOJI.get(work_format, "📍")
        lines.append(f"{fmt_emoji} {work_format.capitalize()}")
    if stack and stack != "not specified":
        lines.append(f"⚙️ {_e(stack)}")
    if reason:
        lines.append(f"\n<i>{_e(reason)}</i>")
    lines.append(f"\n{url}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ В работу", callback_data=f"take:{vacancy_id}"),
        InlineKeyboardButton("❌ Skip",     callback_data=f"skip:{vacancy_id}"),
    ]])
    message = await app.bot.send_message(
        chat_id=config.telegram_chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    _vacancy_repo.save_telegram_message_id(vacancy_id, message.message_id)


async def notify_letter(
    app: Application,
    vacancy_id: int,
    vacancy_title: str,
    company: str,
    apply_url: str,
    body: str,
) -> None:
    preview = body if len(body) <= 3500 else body[:3500] + "\n\n… [truncated]"
    text = (
        f"✉️ <b>Сопроводительное письмо</b>\n"
        f"<b>{_e(vacancy_title)}</b> — {_e(company or 'unknown')}\n\n"
        f"📎 Ссылка: {apply_url}\n"
        f"После отправки: <code>/applied {vacancy_id}</code>\n\n"
        f"---\n\n"
        f"{_e(preview)}"
    )
    await app.bot.send_message(
        chat_id=config.telegram_chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def notify_event(
    app: Application,
    event_id: int,
    title: str,
    event_type: str,
    location: str,
    event_date: str,
    organizer: str,
    description: str,
    url: str,
    score: int,
) -> None:
    type_emoji = _EVENT_TYPE_EMOJI.get(event_type, "📅")
    lines = [f"{type_emoji} <b>Событие</b> — {score}/10\n"]
    lines.append(f"<b>{_e(title)}</b>")
    if organizer:
        lines.append(f"👤 {_e(organizer)}")
    if location:
        lines.append(f"📌 {_e(location)}")
    if event_date:
        lines.append(f"🗓 {_e(event_date)}")
    if description:
        lines.append(f"\n<i>{_e(description)}</i>")
    lines.append(f"\n{url}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("👍 Интересно", callback_data=f"event_interest:{event_id}"),
        InlineKeyboardButton("❌ Пропустить", callback_data=f"event_skip:{event_id}"),
    ]])
    message = await app.bot.send_message(
        chat_id=config.telegram_chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    _event_repo.save_telegram_message_id(event_id, message.message_id)


# --- Callback handler ----------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    action, _, entity_id_str = query.data.partition(":")
    entity_id = int(entity_id_str)

    if action == "take":
        _vacancy_repo.update_status(entity_id, "in_progress")
        await query.edit_message_text(
            f"✅ Вакансия {entity_id} взята в работу. Генерирую письмо…"
        )
        from src.scheduler.jobs import run_research_for_vacancy
        context.application.create_task(
            run_research_for_vacancy(context.application, entity_id)
        )

    elif action == "skip":
        _vacancy_repo.update_status(entity_id, "rejected")
        await query.edit_message_text(f"❌ Вакансия {entity_id} пропущена.")

    elif action == "event_interest":
        _event_repo.update_status(entity_id, "interested")
        await query.edit_message_text(
            f"👍 Событие {entity_id} отмечено как интересное!\n"
            f"После посещения: <code>/attended {entity_id}</code>",
            parse_mode="HTML",
        )

    elif action == "event_skip":
        _event_repo.update_status(entity_id, "skipped")
        await query.edit_message_text(f"❌ Событие {entity_id} пропущено.")

    else:
        log.warning("Unknown callback action: %s", action)


# --- Command handlers ----------------------------------------------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    lines = ["📊 <b>Статус заявок</b>\n"]
    total = 0
    for status in _STATUS_EMOJI:
        count = len(_vacancy_repo.get_by_status(status))
        if count > 0:
            lines.append(f"{_STATUS_EMOJI[status]} {status}: {count}")
            total += count
    lines.append(f"\n<b>Всего:</b> {total}")
    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    vacancies = _vacancy_repo.get_all_by_statuses(["new"])
    if not vacancies:
        await message.reply_text("✅ Нет непросмотренных вакансий.")
        return
    await message.reply_text(
        f"📋 Непросмотренных: <b>{len(vacancies)}</b>", parse_mode="HTML"
    )
    for v in vacancies[:10]:
        assert v.id is not None
        lines = [f"<b>{_e(v.title)}</b>"]
        if v.company:
            lines.append(f"🏢 {_e(v.company)}")
        if v.location:
            lines.append(f"📌 {_e(v.location)}")
        lines.append(f"\n{v.url}")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ В работу", callback_data=f"take:{v.id}"),
            InlineKeyboardButton("❌ Skip",     callback_data=f"skip:{v.id}"),
        ]])
        await message.reply_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=keyboard, disable_web_page_preview=True,
        )
    if len(vacancies) > 10:
        await message.reply_text(
            f"<i>...ещё {len(vacancies) - 10}. Отреагируй на эти, потом /pending снова.</i>",
            parse_mode="HTML",
        )


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    vacancies = _vacancy_repo.get_all_by_statuses(
        ["in_progress", "letter_sent", "applied", "interview", "offer"]
    )
    if not vacancies:
        await message.reply_text("Нет вакансий в работе.")
        return
    lines = ["<b>Вакансии в работе:</b>\n"]
    for v in vacancies:
        emoji = _STATUS_EMOJI.get(v.status, "•")
        company = f" — {_e(v.company)}" if v.company else ""
        lines.append(f"{emoji} <code>{v.id}</code> {_e(v.title)}{company} [{v.status}]")
    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_applied(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    args = context.args
    if not args or not args[0].isdigit():
        await message.reply_text("Использование: /applied &lt;vacancy_id&gt;", parse_mode="HTML")
        return
    vacancy_id = int(args[0])
    _vacancy_repo.update_status(vacancy_id, "applied")
    await message.reply_text(
        f"📤 Вакансия <code>{vacancy_id}</code> отмечена как <b>отправленная</b>. Удачи! 🤞",
        parse_mode="HTML",
    )


async def cmd_interview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    args = context.args
    if not args or not args[0].isdigit():
        await message.reply_text("Использование: /interview &lt;vacancy_id&gt;", parse_mode="HTML")
        return
    _vacancy_repo.update_status(int(args[0]), "interview")
    await message.reply_text(
        f"🎙️ Интервью назначено для вакансии <code>{args[0]}</code>.",
        parse_mode="HTML",
    )


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать новые события (status=new) с кнопками."""
    message = update.message
    if message is None:
        return
    events = _event_repo.get_all_by_statuses(["new"])
    if not events:
        await message.reply_text("✅ Нет новых событий. Запусти /scout_events для поиска.")
        return
    await message.reply_text(
        f"📅 Новых событий: <b>{len(events)}</b>", parse_mode="HTML"
    )
    for ev in events[:10]:
        assert ev.id is not None
        type_emoji = _EVENT_TYPE_EMOJI.get(ev.event_type, "📅")
        lines = [f"{type_emoji} <b>{_e(ev.title)}</b>"]
        if ev.organizer:
            lines.append(f"👤 {_e(ev.organizer)}")
        if ev.location:
            lines.append(f"📌 {_e(ev.location)}")
        if ev.event_date:
            lines.append(f"🗓 {_e(ev.event_date)}")
        lines.append(f"\n{ev.url}")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👍 Интересно", callback_data=f"event_interest:{ev.id}"),
            InlineKeyboardButton("❌ Пропустить", callback_data=f"event_skip:{ev.id}"),
        ]])
        await message.reply_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=keyboard, disable_web_page_preview=True,
        )


async def cmd_attended(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отметить событие как посещённое."""
    message = update.message
    if message is None:
        return
    args = context.args
    if not args or not args[0].isdigit():
        await message.reply_text("Использование: /attended &lt;event_id&gt;", parse_mode="HTML")
        return
    event_id = int(args[0])
    _event_repo.update_status(event_id, "attended")
    await message.reply_text(
        f"✅ Событие <code>{event_id}</code> отмечено как <b>посещённое</b>. 🎉",
        parse_mode="HTML",
    )


async def cmd_scout_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    await message.reply_text("📅 Ищу tech-события в Дании…")
    from src.scheduler.jobs import job_scout_events
    context.application.create_task(job_scout_events(context.application))


async def cmd_scout_jobindex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    await message.reply_text("🔍 Jobindex: запускаю поиск…")
    from src.scheduler.jobs import job_scout_jobindex
    context.application.create_task(job_scout_jobindex(context.application))


async def cmd_scout_linkedin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    await message.reply_text("🔍 LinkedIn: запускаю поиск… (может занять ~30 сек)")
    from src.scheduler.jobs import job_scout_linkedin
    context.application.create_task(job_scout_linkedin(context.application))


async def cmd_scout_remotive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    await message.reply_text("🌐 Remotive: запускаю поиск remote вакансий…")
    from src.scheduler.jobs import job_scout_remotive
    context.application.create_task(job_scout_remotive(context.application))


async def cmd_scout_thehub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    await message.reply_text("🔍 The Hub: запускаю поиск датских tech вакансий…")
    from src.scheduler.jobs import job_scout_thehub
    context.application.create_task(job_scout_thehub(context.application))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    await message.reply_text(
        "🤖 <b>Job Hunter Bot</b>\n\n"
        "<b>Вакансии:</b>\n"
        "/pending — непросмотренные вакансии\n"
        "/done — вакансии в работе\n"
        "/status — статистика по этапам\n\n"
        "<b>Поиск вакансий:</b>\n"
        "/jobindex — Jobindex (датский job board)\n"
        "/linkedin — LinkedIn\n"
        "/remotive — Remotive (remote-only)\n"
        "/thehub — The Hub (датские стартапы)\n\n"
        "<b>События:</b>\n"
        "/events — непросмотренные митапы и конференции\n"
        "/scout_events — запустить поиск событий\n"
        "/attended &lt;id&gt; — отметить как посещённое\n\n"
        "<b>Статусы вакансий:</b>\n"
        "/applied &lt;id&gt; — отметить как отправленное\n"
        "/interview &lt;id&gt; — интервью назначено\n\n"
        "/help — эта справка\n\n"
        "Кнопки: ✅ В работу / ❌ Skip / 👍 Интересно",
        parse_mode="HTML",
    )


# --- App factory ---------------------------------------------------------

def build_app() -> Application:
    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .build()
    )
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("done",      cmd_done))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("jobindex",     cmd_scout_jobindex))
    app.add_handler(CommandHandler("linkedin",     cmd_scout_linkedin))
    app.add_handler(CommandHandler("remotive",     cmd_scout_remotive))
    app.add_handler(CommandHandler("thehub",       cmd_scout_thehub))
    app.add_handler(CommandHandler("events",       cmd_events))
    app.add_handler(CommandHandler("scout_events", cmd_scout_events))
    app.add_handler(CommandHandler("attended",     cmd_attended))
    app.add_handler(CommandHandler("applied",      cmd_applied))
    app.add_handler(CommandHandler("interview",    cmd_interview))
    app.add_handler(CommandHandler("help",         cmd_help))
    return app
