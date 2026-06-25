# Job Hunt Automation

A personal automation system that scrapes job postings and local events, scores them with AI, and notifies me through a Telegram bot. Built to reduce the daily grind of job searching while living in Aarhus, Denmark.

## What it does

1. **Scrapes** job boards every morning (Jobindex, LinkedIn, The Hub, Remotive)
2. **Scores** each vacancy with Claude — checks location fit, tech stack match, and remote policy
3. **Notifies** me in Telegram with a score and reason; I tap "Take to work" or "Skip"
4. **Researches** the company and **writes a cover letter** tailored to my style on demand
5. **Tracks** applications through the full lifecycle (applied → interview → offer)
6. **Finds events** — both professional tech meetups and entertainment (concerts, festivals) in Aarhus and Jutland

Everything is visible in a web dashboard with filters, AI reports, and personal notes per vacancy.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────┐
│                    Telegram Bot (HITL)                   │
│  New vacancy card → [✅ Take to work] or [❌ Skip]       │
└───────────────────────────┬─────────────────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │            Scheduler (APScheduler)   │
         │  08:00 Jobindex  08:10 Remotive      │
         │  08:20 The Hub   08:35 LinkedIn       │
         │  09:10 Tech events  09:30 Fun events  │
         └──────────────────┬──────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │         Scrapers (per source)        │
         │  RSS · REST API · Cookie auth · HTML │
         └──────────────────┬──────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │         ScoutAgent (Claude)          │
         │  Title pre-filter → LLM scoring      │
         │  Location hard filter (Denmark only) │
         └──────────────────┬──────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │           SQLite Database            │
         │  vacancies · community_events        │
         └──────────────────┬──────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │       Web Dashboard (FastAPI+React)  │
         │  Vacancies · Events · Entertainment  │
         └─────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.13, asyncio |
| AI | Anthropic Claude (claude-sonnet-4-6) |
| Telegram bot | python-telegram-bot 22.x |
| Scheduler | APScheduler 3.x (CronTrigger, UTC) |
| Database | SQLite via stdlib sqlite3 (no ORM) |
| Web search | ddgs (DuckDuckGo, no API key) |
| LinkedIn scraping | linkedin-api 2.3.x (cookie auth) |
| Backend API | FastAPI + Uvicorn (port 8080) |
| Frontend | React 18 + TypeScript + Vite |
| Deployment | EC2 t2.micro + GitHub Actions |

---

## Scrapers

Each scraper is an independent class inheriting `BaseScraper` (Open/Closed Principle — adding a new source doesn't touch existing code).

| Source | Method | Notes |
|---|---|---|
| **Jobindex** | RSS feed | Danish job board, per-keyword queries |
| **LinkedIn** | Cookie auth (`li_at` + `JSESSIONID`) | `get_job()` called only for titles that pass pre-filter |
| **The Hub** | REST API | Main Danish tech job board |
| **Remotive** | Public API | Remote-only international jobs |
| **Eventbrite** | HTML → JSON-LD parsing | No API key needed |
| **DuckDuckGo** | Search snippets | Tech events + entertainment events |

---

## AI pipeline

### Vacancy scoring (ScoutAgent)

Before calling Claude, each title goes through a cheap keyword pre-filter (`_is_tech_title()`). Only tech titles proceed to LLM scoring. This saves ~80% of tokens.

The LLM then applies a **hard location filter** before scoring by tech stack:
- ✅ Accept: Denmark (any format) or truly worldwide remote
- ❌ Reject: onsite/hybrid outside Denmark, EU/EMEA-only remote, US-only remote
- Rule: *"If in doubt — reject"*

Rejected vacancies get `score=2` and never reach the notification stage.

### Research + Cover letter pipeline

Triggered manually when I tap "Take to work" in Telegram or click "Generate cover letter" in the dashboard. Two steps:

1. **ResearchAgent** — runs 3 DuckDuckGo queries about the company, builds a dossier with Claude
2. **LetterAgent** — writes a cover letter using my resume + dossier + job description

The letter matches my personal style: warm, direct, with a bit of humor — not corporate. Letters can be regenerated with feedback ("make the opening more specific", "mention Go experience more", etc.). Each regeneration saves as v2, v3... — history is kept in the DB.

**Important:** "Take to work" and "Generate cover letter" are decoupled. Clicking "Take to work" just changes the status instantly. The AI pipeline runs separately on demand. You can mark a job as applied without ever generating a letter.

### Event scouting

Two categories, same infrastructure, different prompts:

**Professional events** (tech meetups, conferences):
- Sources: Eventbrite HTML scraping + DuckDuckGo web search
- Agent scores by networking value for Aarhus-based backend engineer
- Notifies via Telegram

**Entertainment events** (concerts, festivals, theater, outdoor):
- Source: DuckDuckGo (queries for Aarhus + eastern Jutland)
- Agent scores by proximity and personal taste
- No Telegram — dashboard only

Both agents receive today's date explicitly in the prompt (since the system prompt is cached and can't carry dynamic info). Past events are also filtered in code as a second defense layer.

---

## Database schema (SQLite, versioned migrations)

### vacancies

| Column | Description |
|---|---|
| `source_id` | Unique per scraper (sha1 of URL, `li_job_id`, etc.) |
| `status` | `new → in_progress → letter_sent → applied → interview → offer → rejected → rejected_by_company` |
| `platform` | jobindex / linkedin / thehub / remotive |
| `work_format` | remote / hybrid / onsite |
| `company_report` | Cached AI company dossier (V9) |
| `match_analysis` | Cached AI match analysis vs resume (V10) |
| `notes` | Personal notes, free text (V11) |

### community_events

| Column | Description |
|---|---|
| `category` | `professional` (tech) or `entertainment` (V12) |
| `status` | `new → interested → attending → attended → skipped` |
| `event_date` | ISO date, NULL if unknown |
| `score` | 1–10 from LLM |
| `source` | eventbrite / web |

Migrations are versioned (V1–V12) and run automatically on startup. OCP applies: new migrations are append-only.

---

## Web dashboard

**URL:** `http://3.75.175.202:8080` (or `localhost:8080`)  
**Auth:** HTTP Basic Auth

### Vacancies page
Table view with filters by status and platform. Click any row to open the detail page.

### Vacancy detail page
- **Status action bar** — contextual buttons based on current status
- **✉️ Cover letter** — generate on demand, regenerate with written feedback
- **🏢 Company report** — AI dossier from web search (cached in DB)
- **🎯 Match analysis** — how well my resume fits this specific role (cached in DB)
- **📝 My notes** — personal textarea, saved to DB

### Events page
Tech meetups and professional events. Cards with inline status buttons.

### 🎠 Entertainment page
Concerts, festivals, outdoor events in Aarhus and Jutland. Same card UI.

---

## Deployment

Push to `main` → GitHub Actions → SSH into EC2 → `git pull` + `pip install` + `npm build` + `systemctl restart` + Telegram notification.

Two systemd services on EC2:
- `job-hunt.service` — Telegram bot + scheduler
- `job-hunt-dashboard.service` — FastAPI dashboard

---

## Project structure

```
main.py                              Entry point, scheduler wiring
resume.md                            My resume — injected into every agent system prompt
requirements.txt

src/
  config.py                          Config dataclass, reads .env
  event_utils.py                     Shared date filter utility
  database/
    schema.py                        DDL + versioned migrations V1–V12
    repository.py                    VacancyRepository, CommunityEventRepository
  agents/
    base_agent.py                    BaseAgent: LLM call with prompt caching
    scout_agent.py                   Vacancy scoring
    research_agent.py                Company research
    letter_agent.py                  Cover letter generation
    event_scout_agent.py             Professional event scoring
    entertainment_scout_agent.py     Entertainment event scoring
  scrapers/
    jobindex_scraper.py
    linkedin_scraper.py
    thehub_scraper.py
    remotive_scraper.py
    eventbrite_scraper.py
    event_scraper.py                 DuckDuckGo for tech events
    entertainment_scraper.py         DuckDuckGo for entertainment events
  bot/
    telegram_bot.py                  All Telegram UI
  scheduler/
    jobs.py                          Cron job functions

dashboard/
  api/
    main.py                          FastAPI app, SPA routing
    pipeline.py                      AI pipeline functions
    routers/
      vacancies.py
      events.py
      stats.py
  frontend/                          React + TypeScript + Vite
    src/
      pages/
        DashboardPage.tsx
        VacanciesPage.tsx
        VacancyDetailPage.tsx
        EventsPage.tsx
        EntertainmentPage.tsx
```

---

## Key design decisions

**Blocking calls in threads.** All scrapers, agents, and DB writes are blocking. They run in `asyncio.to_thread()` so the Telegram polling loop never blocks.

**Prompt caching.** The agent system prompt (which includes my full resume) is marked `cache_control: ephemeral`. It gets cached by Anthropic's API across calls in the same session, reducing token cost significantly.

**Hard filters before LLM.** Both title pre-filter and location filter run before any LLM call. Cuts token usage by ~80% and makes rejection reasons explicit in logs.

**Deduplication via upsert.** Each scraper source has a unique `source_id`. `upsert()` returns `(id, is_new)`. Notifications fire only on `is_new=True`.

**Past events filtered at two levels.** The LLM receives today's date in the user prompt and is instructed to exclude past events. The code also checks `event_date < today` after parsing the LLM response — defense in depth.

**SPA routing.** FastAPI serves `/assets` as static files (with proper cache headers). A catch-all `/{full_path:path}` route returns `index.html` for everything else. `StaticFiles(html=True)` mounted at `/` doesn't work for browser refresh on deep routes like `/vacancies/42`.
