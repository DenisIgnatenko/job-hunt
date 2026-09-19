# job-hunt — Project Context

## Purpose
Job search automation for Denis Ignatenko (backend engineer, Aarhus, Denmark).
Vacancy + event scraping → AI scoring → company research → cover letter generation
→ HITL via a Telegram bot. A web dashboard manages the whole pipeline.

## Stack
- Python 3.13, asyncio (every blocking call goes through asyncio.to_thread)
- Anthropic SDK (claude-sonnet-4-6) — scoring, research, letters, events
- python-telegram-bot 22.x — HITL notifications
- APScheduler 3.x — CronTrigger (not IntervalTrigger), UTC
- SQLite, sqlite3 stdlib (no ORM in the schema layer)
- linkedin-api 2.3.x — LinkedIn via cookie auth (job search + outreach people search)
- **ddgs** (formerly duckduckgo-search, renamed) — web search in ResearchAgent, EventScoutAgent, EntertainmentScoutAgent
- FastAPI + Uvicorn — dashboard API (port 8080)
- React 18 + TypeScript + Vite — dashboard SPA
- requests, python-dotenv, Axios

## Running

### Telegram bot (main process)
```bash
cd job-hunt
.venv/bin/python main.py
```

### Dashboard (separate process)
```bash
cd job-hunt
.venv/bin/python -m uvicorn dashboard.api.main:app --port 8080
```

### EC2 (deployment)
- IP: 3.75.175.202 (eu-central-1, t2.micro)
- Bot: systemd `job-hunt.service`
- Dashboard: systemd `job-hunt-dashboard.service`
- Repo: git@github.com:DenisIgnatenko/job-hunt.git
- **Automatic deploy**: `git push origin main` → GitHub Actions → SSH → git pull + pip install + npm build + restart + Telegram notification
- Workflow: `.github/workflows/deploy.yml`
- GitHub Secrets: `EC2_HOST`, `EC2_SSH_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- SSH key: `~/.ssh/job-hunt-key.pem`
- Manual deploy (fallback): `bash ~/job-hunt/deploy/update.sh` (bot only, no frontend)

### Diagnosing a gap after time away
The production DB lives on EC2 (`~/job-hunt/job_hunt.db`). The local `job_hunt.db` is a
dev snapshot that drifts from prod — don't confuse the two when cleaning up data.
```bash
ssh -i ~/.ssh/job-hunt-key.pem ubuntu@3.75.175.202
systemctl is-active job-hunt.service job-hunt-dashboard.service
journalctl -u job-hunt.service -n 50 --no-pager | grep -v getUpdates   # skip polling noise
sudo systemctl start job-hunt.service
```
Both units are `enabled`, but that doesn't mean they're running — if the service was
stopped manually (`systemctl stop`), it stays down. In the logs that looks like a clean
`signal=TERM` with no traceback: distinguish that from an actual crash. The dashboard can
be up while the bot is dead — "the site loads" doesn't mean the pipeline is alive; check
`MAX(fetched_at)` in the DB instead.

Before touching data in prod: `sqlite3 job_hunt.db ".backup job_hunt.db.backup-$(date +%Y%m%d-%H%M%S)"`
(a consistent snapshot even while the dashboard is running, unlike `cp`).

Also worth checking after any gap: Anthropic API credit balance. A `400
invalid_request_error: Your credit balance is too low` shows up as `<job> scout failed`
in the logs for every scheduled job on the same day — it looks alarming but is a billing
issue, not a code issue. Confirm with a minimal `messages.create()` call using the same
key, top up if needed, then re-run that day's scraper jobs manually to backfill anything
missed (there's no automatic retry).

### Dependencies are not pinned
`requirements.txt` only has lower bounds (`anthropic>=0.40.0`). Rebuilding the venv pulls
fresh majors — this once jumped `anthropic` to 1.x (moved to `httpx2` internally; the
project doesn't touch httpx directly, and `messages.create` + `cache_control` didn't
change). After recreating the venv, run a smoke test: import the agents, `run_migrations()`,
one live LLM call.

## File structure
```
main.py                          Entry point, wires scheduler + bot
resume.md                        Denis's resume (read at startup, injected into every agent's system prompt)
pyrightconfig.json                basedpyright (typeCheckingMode: standard)
requirements.txt                  Dependencies (ddgs, not duckduckgo-search); unpinned versions
.github/workflows/deploy.yml      GitHub Actions: auto-deploy on push to main
deploy/
  update.sh                       Manual bot update on EC2 (fallback)
  job-hunt.service                 systemd unit for the bot
  job-hunt-dashboard.service       systemd unit for the dashboard

src/config.py                     Config dataclass (frozen), .env → single source of truth
src/database/schema.py            DDL + versioned migrations V1-V14 (run_migrations at startup)
src/database/repository.py        VacancyRepository, CommunityEventRepository, OutreachContactRepository (Repository pattern)
src/event_utils.py                is_past_event_date() — shared past-event filter (DRY)

src/agents/base_agent.py          BaseAgent: _chat() with prompt caching (cache_control: ephemeral)
src/agents/voice.py               DENIS_VOICE (shared "voice" block for LetterAgent + OutreachAgent),
                                   extract_json_object(), has_dash() — see architectural decisions
src/agents/scout_agent.py         ScoutAgent: title pre-filter + LLM scoring → ScoredVacancy
src/agents/research_agent.py      ResearchAgent: ddgs (3 queries) + LLM dossier
src/agents/letter_agent.py        LetterAgent: cover letter in Denis's voice (180-230 words, no em dashes,
                                   see "Denis's personality"), accepts user_comments for regeneration
src/agents/event_scout_agent.py   EventScoutAgent: batch LLM scoring of tech events (category=professional)
src/agents/entertainment_scout_agent.py  EntertainmentScoutAgent: batch LLM scoring of leisure events in Aarhus/Jutland (category=entertainment)
src/agents/outreach_scout_agent.py  OutreachScoutAgent: batch LLM extraction + classification of people
                                     (tech_lead|hiring_manager|hr|other) from web search, confidence >= 6
src/agents/outreach_agent.py      OutreachAgent: drafts a LinkedIn connection-request note
                                   (200-260 chars, no dashes, always sent by Denis manually)

src/scrapers/base_scraper.py        BaseScraper (ABC)
src/scrapers/jobindex_scraper.py    Jobindex RSS, keyword search
src/scrapers/linkedin_scraper.py    LinkedIn via cookie auth (li_at + JSESSIONID)
src/scrapers/thehub_scraper.py      The Hub REST API v2, the main Danish tech job board
                                     (URL and description are assembled separately — see architectural decisions)
src/scrapers/remotive_scraper.py    Remotive public API, remote-only jobs
src/scrapers/eventbrite_scraper.py  Eventbrite HTML → JSON-LD parsing, no API key needed
src/scrapers/event_scraper.py       ddgs search for tech events
src/scrapers/entertainment_scraper.py  ddgs search for leisure events (concerts, festivals, theater)
src/scrapers/outreach_finder.py     finds people at a company: ddgs (site:linkedin.com/in) first,
                                     linkedin_api.search_people() as a fallback

src/bot/telegram_bot.py           All Telegram UI (parse_mode="HTML" everywhere)
src/scheduler/jobs.py             Job functions: scout_jobindex, scout_remotive, scout_thehub,
                                   scout_linkedin, scout_events, scout_entertainment, run_research_for_vacancy

dashboard/api/main.py             FastAPI app: run_migrations(), SPA catch-all, CORS, no docs
dashboard/api/pipeline.py         run_research_pipeline(), regenerate_letter(),
                                   generate_company_report(), generate_match_analysis(),
                                   find_outreach_contacts(), draft_outreach_message()
dashboard/api/models.py           Pydantic request/response models
dashboard/api/routers/
  vacancies.py                    GET/PATCH /api/vacancies, PATCH /notes,
                                   POST generate-letter/regenerate-letter/company-report/match-analysis,
                                   POST find-outreach-contacts (vacancy-scoped, lives here — see decisions)
  events.py                       GET /api/events?category=, PATCH /api/events/{id}/status
  outreach.py                     POST /api/outreach/{id}/draft-message, PATCH /{id}/status
                                   (contact-scoped, doesn't fit the /api/vacancies/{vacancy_id} prefix)
  stats.py                        GET /api/stats
dashboard/frontend/               React SPA (Vite build → dist/)
  src/api/client.ts               axios with Basic Auth interceptors, AI_TIMEOUT=90000ms
  src/pages/VacanciesPage.tsx
  src/pages/VacancyDetailPage.tsx  statuses, action buttons (decoupled from letter generation),
                                    AI reports, notes, status override, letter regeneration with feedback,
                                    🤝 Outreach contacts section (find → draft → copy → mark sent)
  src/pages/EventsPage.tsx        professional events (category=professional)
  src/pages/EntertainmentPage.tsx  leisure events (category=entertainment)
  src/pages/DashboardPage.tsx
  src/components/Navbar.tsx       Dashboard | Vacancies | Events | 🎠 Entertainment
```

## Database (SQLite)

### Table: vacancies
```
id, source_id (UNIQUE), title, company, location, url, description,
posted_at, fetched_at, status, telegram_message_id,
platform, work_format, city,      ← V5, V6, V7
company_report,                   ← V9 (TEXT, NULL until generated)
match_analysis,                   ← V10 (TEXT, NULL until generated)
notes,                            ← V11 (TEXT, NULL — Denis's personal notes)
score                             ← V13 (INTEGER 1-10 from ScoutAgent, NULL for
                                     records predating the migration — badge in the dashboard)
```
- `platform`: "jobindex" | "linkedin" | "thehub" | "remotive" | "unknown"
- `work_format`: "remote" | "hybrid" | "onsite" | "unknown"
- `source_id`: sha1(url) for Jobindex, "li_{job_id}" for LinkedIn, "thehub_{id}", "remotive_{id}"

### Table: community_events (V8)
```
id, title, url (UNIQUE), event_type, location, event_date (ISO),
description, organizer, score, status, source, fetched_at, telegram_message_id,
category                          ← V12 ("professional" | "entertainment", DEFAULT 'professional')
```
- `status`: "new" | "interested" | "attending" | "attended" | "skipped"
- `source`: "eventbrite" | "web"
- `category`: "professional" (tech meetups) | "entertainment" (concerts, festivals)

### Table: outreach_contacts (V14)
```
id, vacancy_id (FK vacancies), company, full_name, headline,
role_category, linkedin_url (UNIQUE), source, message_draft,
status, fetched_at
```
- `role_category`: "tech_lead" | "hiring_manager" | "hr" | "other"
- `source`: "web" (ddgs) | "linkedin" (search_people fallback)
- `status`: "new" | "drafted" | "sent" | "replied" | "skipped"
- `linkedin_url` — dedup key, like `source_id` on vacancies / `url` on events
- `sent` is set by Denis manually after he sends the message himself from LinkedIn —
  there's nothing in this table resembling an "auto-sent" flag or timestamp

### Vacancy statuses (full lifecycle)
```
new → in_progress → letter_sent → applied → interview → offer → rejected → rejected_by_company
```
Dashboard: "in_progress" and "letter_sent" render identically (an internal-only distinction).

### Migrations
V1-V4: vacancies, companies, cover_letters, events (audit log) tables
V5: platform, V6: work_format, V7: city
V8: community_events, V9: company_report, V10: match_analysis, V11: notes
V12: category on community_events (DEFAULT 'professional', existing rows untouched)
V13: score on vacancies (INTEGER, NULL for existing rows — scores aren't backfilled)
V14: outreach_contacts — people found for outreach on a given vacancy
OCP: new migrations are appended only — existing ones are never edited.

## Schedule (CronTrigger, UTC)
```
06:00 UTC = 08:00 CEST  Jobindex
06:10 UTC = 08:10 CEST  Remotive
06:20 UTC = 08:20 CEST  The Hub
06:35 UTC = 08:35 CEST  LinkedIn      (slower — cookies + get_job() per vacancy)
07:10 UTC = 09:10 CEST  Events        (Eventbrite HTML + ddgs + LLM, category=professional)
07:30 UTC = 09:30 CEST  Entertainment (ddgs + LLM, category=entertainment, no Telegram)
```
Results are ready by 10:00 CEST. The overnight run doesn't wake Denis up.

## Telegram commands
```
/pending      unreviewed vacancies (status=new)
/done         vacancies in progress (in_progress, letter_sent, applied, interview, offer)
/status       counts across all statuses
/jobindex     run Jobindex manually
/remotive     run Remotive manually
/thehub       run The Hub manually
/linkedin     run LinkedIn manually
/events       list events from the DB
/scout_events run event scraping manually (Eventbrite + ddgs)
/attended     mark an event as attended
/help         help text
```

## Dashboard (http://3.75.175.202:8080 or localhost:8080)
- HTTP Basic Auth (DASHBOARD_USER / DASHBOARD_PASSWORD)
- Tabs: Dashboard, Vacancies, Events (professional), 🎠 Entertainment
- Status filters; events are filtered by category at the API level
- VacanciesPage (list view): a score column (V13 — green/yellow/red badge)
  and an inline ❌ Reject button on every row (stopPropagation, instant, no page reload)
- Events and Entertainment — cards with inline status buttons (new/interested/attending/attended/skipped)
- Vacancy detail page:
  - **Action bar**: `⚙️ Take to work` (instant, status only) · `📤 Mark applied` · `❌ Reject`, etc.
  - **✉️ Cover letter section**: `✨ Generate cover letter` button (AI pipeline, ~20 sec) — separate from the action bar
  - `✏️ Regenerate with feedback` — regenerate with a written comment
  - "📝 My notes" — free-text textarea (PATCH /notes, stored in DB V11)
  - Job description (HTML or plain text via descriptionToHtml())
  - Letter versioning: v1, v2, v3... — iteration history kept in the DB
  - **🤝 Outreach contacts section**: `🔍 Find contacts` (ddgs + LinkedIn fallback) → a card per
    person (name, role, LinkedIn link) → `✍️ Draft message` → editable textarea →
    `📋 Copy` → Denis sends it himself from LinkedIn → `✅ Mark sent`. No auto-send anywhere in the UI.
- AI sections (cached in DB V9/V10):
  - "Company report" — 3 ddgs queries + LLM (max_tokens=1400)
  - "Match analysis" — resume-to-vacancy comparison (max_tokens=1200)
- The "🔄 Regenerate" button clears the cache and shows the generate button again

## Data flow (vacancies)
```
scraper.fetch()
  → title pre-filter (_is_tech_title) — no LLM, free
  → [LinkedIn only] get_job() for titles that passed the filter (company, location, description)
  → ScoutAgent.run() → LLM scoring → ScoredVacancy(vacancy, score, reason, work_format, stack)
  → VacancyRepository.upsert() → (id, is_new)
  → is_new=True → notify_vacancy() on Telegram
  → Denis: [✅ Take to work] → status=in_progress (instant, no AI)
  → Denis: [✨ Generate cover letter] → run_research_pipeline()
    → ResearchAgent (ddgs + LLM) → company dossier
    → LetterAgent (resume + dossier + job description) → CoverLetter → status=letter_sent
  → Denis: [📤 Mark applied] → status=applied (independent of whether a letter exists)
```

## Data flow (professional events)
```
EventbriteScraper.fetch() → list[CommunityEvent] (JSON-LD from HTML, scored by location)
  → is_past_event_date() hard filter — past events are cut before the LLM sees them
EventScraper.fetch()      → list[dict] (ddgs snippets)
  → EventScoutAgent.run(today=date.today()) → list[ScoredEvent]
     — today goes in the user prompt, is_past_event_date() re-checked in code (defense in depth)
     — score >= 5 → category='professional'
CommunityEventRepository.upsert() → (id, is_new)
  → is_new=True → notify_event() on Telegram
Denis: status buttons on the dashboard or in Telegram
```

## Data flow (entertainment events)
```
EntertainmentScraper.fetch() → list[dict] (ddgs: concerts, festivals, theater in Aarhus/Jutland)
  → EntertainmentScoutAgent.run(today=date.today()) → list[ScoredEvent]
     — today in the user prompt, is_past_event_date() in code
     — score >= 5 → category='entertainment'
     — max_tokens=2500 (8 queries return ~60 results)
CommunityEventRepository.upsert() → (id, is_new)
  → No Telegram notifications — dashboard only
Denis: status buttons on the Entertainment page
```

## Data flow (outreach)
```
Denis on a vacancy card: [🔍 Find contacts]
  → OutreachFinder.find(company): ddgs (site:linkedin.com/in, 2 query groups by role)
     → if empty: linkedin_api.search_people() fallback, ONLY then, once
  → OutreachScoutAgent.run(): a single batch LLM call, strict confidence >= 6 filter
     (ddgs returns a lot of noise — unrelated people, stale positions; the model must
     reject anything that isn't clearly "currently at this company, in a relevant role")
  → OutreachContactRepository.upsert() → (id, is_new), dedup on linkedin_url
Denis on a contact card: [✍️ Draft message]
  → OutreachAgent.run(contact, vacancy) → LinkedIn connection-request note, 200-260 chars
  → save_message_draft() → status='drafted'
Denis: edits in the textarea if needed → [📋 Copy] → pastes it and sends it HIMSELF from LinkedIn
  → [✅ Mark sent] → status='sent' (nothing is sent by the system automatically)
```

## Key architectural decisions

### Async
All blocking calls (scrapers, agents, sqlite) run through `asyncio.to_thread()`.
The event loop never blocks — Telegram polling keeps running.

### Deduplication
`upsert()` returns `(id, is_new)`. Notifications fire only when `is_new=True`.
`UNIQUE` constraint on `source_id` (vacancies) and `url` (events).

### Pre-filter before the LLM
`_is_tech_title()` in scout_agent.py filters out non-tech vacancies before calling Claude.
LinkedIn: `get_job()` is only called for titles that pass the title filter.
Saves roughly 80% of tokens on scoring.

### Scout — location hard filter
ScoutAgent applies location rules BEFORE scoring against the tech stack.
Reject: onsite/hybrid outside Denmark; remote with any regional restriction (EU, EMEA, Europe, US, UK, etc.).
Accept: Denmark only (any format) OR remote with no geographic restriction at all (worldwide/global/unspecified).
"If in doubt — reject" is an explicit instruction in the prompt.
Rejected vacancies get score=2, relevant=false — they never reach the notification stage.

### Events — hard date filter
`src/event_utils.py::is_past_event_date(event_date, today)` — a shared utility (DRY).
Used in: EventbriteScraper.fetch(), EventScoutAgent.run(), EntertainmentScoutAgent.run().
`today` is passed explicitly in the user prompt (the system prompt is cached and can't carry a date).
Defense in depth: the LLM is instructed to reject past events, and the code re-checks too.
An unknown date (None) is not rejected (no data ≠ past).

### Event categories (V12)
community_events.category = 'professional' | 'entertainment'.
One repository, one API endpoint — filtered via the ?category= query param.
`get_all_by_statuses(statuses, category=None)` — category=None returns everything.
The entertainment job does NOT send Telegram notifications — it only writes to the DB for the dashboard.

### Description storage
Scrapers store the full description, untruncated (the old [:2000] truncation was removed).
ScoutAgent truncates to [:800] itself, only for its own LLM call.
Frontend: descriptionToHtml() — if there are no HTML tags (LinkedIn, Remotive), converts \n\n into <p>.

### LetterAgent — decoupled from "Take to work"
`⚙️ Take to work` → just `updateVacancyStatus(id, 'in_progress')` (instant).
`✨ Generate cover letter` — a separate button in the letter section, triggers the AI pipeline (~20 sec).
`📤 Mark applied` can be clicked without ever generating a letter — nothing blocks it.
Same pattern as the Company report and Match analysis sections (SRP).

### LetterAgent — regeneration with feedback
`LetterAgent.run(vacancy, company, user_comments)` — user_comments is appended to the prompt.
`pipeline.regenerate_letter(vacancy_id, comments)` — no repeat research.
Versioning: every regeneration is saved as v2, v3, etc. — history stays in the DB.

### Prompt caching
`BaseAgent._chat()` caches the system prompt via `cache_control: ephemeral`.
The system prompt (which includes the full resume) is built once, in the agent's `__init__`.
The date (today) goes in the user prompt, not the system prompt — otherwise the cache would invalidate daily.

### EventScoutAgent / EntertainmentScoutAgent — batch vs. per-item
A single LLM call for the whole batch of events (not per-item like ScoutAgent).
Cheaper: events matter less than vacancies, and lower accuracy is an acceptable tradeoff there.
`extract_json_object()` (in `voice.py`): uses `find('{')` / `rfind('}')` to pull out the JSON —
more reliable than a `{.*?}` regex, which stops at the first `}` inside a nested object.

### AI reports cached in the DB
company_report and match_analysis are stored in the DB (V9, V10).
The dashboard loads them when a card is opened — no tokens spent on repeat views.
"🔄 Regenerate" clears the field in local state (not the DB) → shows the generate button → a new POST → saves to the DB.

### Dashboard SPA routing
`dashboard/api/main.py`: `/assets` is mounted as StaticFiles (JS/CSS with proper cache headers).
A catch-all `/{full_path:path}` route returns `index.html` — needed for a browser refresh on /vacancies/42, etc.
`StaticFiles(html=True)` mounted at "/" does NOT work for an SPA — it looks for a literal file at that path.

### Dashboard auth
`secrets.compare_digest()` — protects against timing attacks.
Credentials live in the browser's sessionStorage — cleared when the tab closes.
`verifyCredentials()` uses a plain axios instance (no interceptors) to check credentials at login —
otherwise the 401 interceptor would trigger a reload before the catch block could show an error.

### OCP on scrapers
A new scraper is a new class inheriting `BaseScraper`.
Existing code doesn't change (jobs.py picks up a new scraper via an import + add_job).

### Outreach — LinkedIn draft-only, no auto-send (added 2026-09-14)
`linkedin_api` (already a project dependency, already used for job scraping) technically supports
`search_people`, `get_profile`, `add_connection`, `send_message` — full automation is possible.
Deliberately not doing it: LinkedIn's Automation Policy explicitly bans scripted messaging and
connection requests, and it's actively detected. Current usage (job scraping via cookie auth) is
already a gray area Denis accepts; auto-sending from a personal account is a materially different
risk — an account restriction would hit right in the middle of active job searching, which is
worse than losing one vacancy source.
Resolution: the system finds people and prepares a draft; Denis copies it and sends it himself
from the LinkedIn UI. There is no `send_message()` or `add_connection()` call anywhere in the code.
Contact sourcing: ddgs (public web search, doesn't touch the LinkedIn session) first,
`search_people()` as a fallback, and only once per "Find contacts" click (not scheduled, not
batched) — LinkedIn-side activity stays low and human-paced.

### DENIS_VOICE — shared "voice" module (DRY)
`src/agents/voice.py` — the "who Denis is" block plus the dash ban, extracted out of
letter_agent.py when OutreachAgent was added (2026-09-14): both agents need to sound like the
same person, and duplicating the prompt text in two places would mean tuning tone twice on
every edit. This module also holds `extract_json_object()` (find/rfind instead of a non-greedy
regex — the same fix already applied in the event/entertainment scout agents, now shared instead
of a third copy).

**has_dash() — defense in depth against dashes.** An instruction to "never use a dash" doesn't
guarantee compliance: while building OutreachAgent, the model copied an en dash (–) straight out
of a vacancy title ("Software Engineer – Integrations") that was in the prompt as context — and
separately, on clean data with no dash in the source, it still occasionally inserted its own em
dash as a rhetorical device (about 1 run in 3). The code now re-checks the result and does one
retry naming the specific problem — the same principle as `is_past_event_date()` (instruct the
LLM AND verify in code). Applied in both LetterAgent and OutreachAgent. Note: the rule needs to
ban the actual characters (— or –), not just the em dash — the original wording named both but
only gave the em dash as an example, so an en dash copied from other text slipped through
unnoticed.

### TheHub — migrated to API v2 (2026-09-04)
`https://thehub.io/api/jobs` started returning 404 — TheHub moved search to `/api/v2/jobs`
without any announcement. Found because vacancies from TheHub had stopped arriving (the bot had
been silent for 2 months, and the API changed sometime in that window). The `docs[]` response
shape is the same, but `absoluteJobUrl` and `description` disappeared:
- The URL is now built manually from `id`: `https://thehub.io/jobs/{id}` (verified against the
  links on the listing page)
- `description` is fetched with a separate request to the job's detail page — it has JSON-LD
  (`schema.org JobPosting`), the same technique `EventbriteScraper` uses for events
- Enrichment only runs for vacancies that pass `_is_tech_title()` — same pattern as
  `LinkedInScraper._enrich_descriptions()`, to avoid spending extra requests on vacancies that
  are clearly irrelevant anyway
- The attribute order in the `<script>` tag on TheHub's pages is non-standard (`data-hid` comes
  before `type`) — the regex isn't order-dependent, it matches any `ld+json` block and checks
  `@type` after `json.loads()`

Lesson: third-party job board APIs change without notice. If vacancies from a source suddenly
stop showing up (0 fetched in the logs where there used to be some), check the scraper's response
directly with `curl` first, before assuming the scoring logic broke.

### FIX: dashboard/api/pipeline.py was importing the old package name (2026-09-14)
`from duckduckgo_search import DDGS` instead of `from ddgs import DDGS` — the only place in the
project still using the old import; everything else had already moved to `ddgs`. This raised
`ModuleNotFoundError` on any call into pipeline.py, including the dashboard's "Company report"
button — it had been silently broken in production. Found while adding the outreach functions to
the same file: `find_outreach_contacts()` wouldn't have worked either without fixing this import
first.

## .env variables
```
ANTHROPIC_API_KEY
ANTHROPIC_MODEL=claude-sonnet-4-6
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
DATABASE_URL=sqlite:///job_hunt.db
SCOUT_INTERVAL_HOURS=6
JOBINDEX_KEYWORDS=Java developer,Go developer,Golang,Node.js backend,Spring Boot,Fullstack developer,Backend engineer,Softwareudvikler
JOBINDEX_LOCATION=
LINKEDIN_EMAIL
LINKEDIN_PASSWORD
LINKEDIN_COOKIE=<li_at cookie>
LINKEDIN_JSESSIONID=<JSESSIONID cookie>
LINKEDIN_INTERVAL_HOURS=12
DASHBOARD_USER=denis
DASHBOARD_PASSWORD=<secret>
RESUME_PATH=resume.md
```

## Denis's personality (for letter_agent)
Open, warm, empathetic. An introvert who's good at communicating (it costs him energy).
His humor is dry and understated, closer to Danish humor than American enthusiasm — deadpan,
never forced. He's lived in Aarhus long enough to have opinions about flat hierarchies and
Danish directness — but that's background texture, not a running joke in every letter. His
YouTube channel @midlifecode (1300+ subscribers) comes up when it's relevant, not as a stock
fact. Open to relocating anywhere — no drama, stated plainly ("happy to relocate", not "would
need some conversation"). Memorable, vivid. Letters should read like an actual message to a
person, not an essay written to impress.

**2026-09-04 — rewrote the prompt (`src/agents/letter_agent.py`).** LetterAgent used to produce
technically fine but "AI-sounding" letters: 250-320 words, heavy em-dash use, "It's not X, it's
Y" constructions, a recap of 2-3 companies straight out of the résumé, and the same boilerplate
closing about a work permit/Aarhus/YouTube in every single letter. The abstract "dry wit"
instruction in the prompt didn't work — there was no humor at all. What changed:
- **Dashes are banned explicitly** — a direct request from Denis: it's the biggest single tell of
  AI-written text (this lines up with a personal formatting preference of his, applied here to
  text an LLM generates, not to my own replies)
- Length cut to 180-230 words (was 250-320)
- The prompt now lists the specific clichés observed as things to avoid — an abstract instruction
  about tone didn't work, concrete examples of bad phrasing did
- Relocation: used to be "only mention it if the location is ambiguous" → now stated plainly and
  confidently, since Denis is genuinely open to relocating anywhere

## Not yet implemented (possible next steps)
- Indeed scraper
- Greenhouse/Lever API for company career pages
- Meetup RSS (not available without a Pro subscription)
- Break dashboard stats down by event category (currently all events are counted together)
- Email outreach (deliberately deferred — sourcing personal email addresses is noticeably more
  GDPR-sensitive than surfacing public LinkedIn profiles via ddgs; revisit separately if the
  LinkedIn draft flow proves useful)
- Telegram notifications for outreach (dashboard-only for now, following the Entertainment
  precedent — adding a notify_* call would be trivial if push notifications for new contacts
  are wanted)
- Standalone outreach for a company with no linked vacancy (currently always starts from a
  vacancy, which gives the message something concrete to reference)
