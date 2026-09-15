# job-hunt — контекст проекта

## Назначение
Автоматизация поиска работы для Denis Ignatenko (backend engineer, Aarhus, Denmark).
Парсинг вакансий + событий → AI-скоринг → исследование компаний → генерация сопроводительного
письма → HITL через Telegram бот. Веб-дашборд для управления пайплайном.

## Стек
- Python 3.13, asyncio (все blocking вызовы через asyncio.to_thread)
- Anthropic SDK (claude-sonnet-4-6) — скоринг, research, письма, events
- python-telegram-bot 22.x — HITL уведомления
- APScheduler 3.x — CronTrigger (не IntervalTrigger), UTC
- SQLite, sqlite3 stdlib (без ORM в schema layer)
- linkedin-api 2.3.x — LinkedIn scraping через cookie-auth (job search + outreach people search)
- **ddgs** (бывший duckduckgo-search, переименован) — веб-поиск в ResearchAgent, EventScoutAgent, EntertainmentScoutAgent
- FastAPI + Uvicorn — дашборд API (порт 8080)
- React 18 + TypeScript + Vite — дашборд SPA
- requests, python-dotenv, Axios

## Запуск

### Telegram бот (основной процесс)
```bash
cd "/Users/iregent/Documents/job-search/job-hunt"
.venv/bin/python main.py
```

### Дашборд (отдельный процесс)
```bash
cd "/Users/iregent/Documents/job-search/job-hunt"
.venv/bin/python -m uvicorn dashboard.api.main:app --port 8080
```

### EC2 (деплой)
- IP: 3.75.175.202 (eu-central-1, t2.micro)
- Бот: systemd `job-hunt.service`
- Дашборд: systemd `job-hunt-dashboard.service`
- Repo: git@github.com:DenisIgnatenko/job-hunt.git
- **Деплой автоматический**: `git push origin main` → GitHub Actions → SSH → git pull + pip install + npm build + restart + Telegram уведомление
- Workflow: `.github/workflows/deploy.yml`
- GitHub Secrets: `EC2_HOST`, `EC2_SSH_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- SSH ключ: `~/.ssh/job-hunt-key.pem`
- Ручной деплой (fallback): `bash ~/job-hunt/deploy/update.sh` (только бот, без фронтенда)

### Диагностика после перерыва
Боевая БД — на EC2 (`~/job-hunt/job_hunt.db`). Локальная `job_hunt.db` — dev-слепок,
расходится с продом; не путать при чистке данных.
```bash
ssh -i ~/.ssh/job-hunt-key.pem ubuntu@3.75.175.202
systemctl is-active job-hunt.service job-hunt-dashboard.service
journalctl -u job-hunt.service -n 50 --no-pager | grep -v getUpdates   # без polling-шума
sudo systemctl start job-hunt.service
```
Оба юнита `enabled`, но ребута не было с 04.06.2026 — если сервис остановили руками
(`systemctl stop`), он так и останется лежать. В логах это чистый `signal=TERM` без трейсбека:
отличать от падения. Дашборд может работать при мёртвом боте — «сайт открывается»
не означает, что пайплайн живой; проверять по `MAX(fetched_at)` в БД.

Перед любой правкой данных на проде: `sqlite3 job_hunt.db ".backup job_hunt.db.backup-$(date +%Y%m%d-%H%M%S)"`
(консистентный снимок при работающем дашборде, в отличие от `cp`).

### Зависимости не запинены
В `requirements.txt` только нижние границы (`anthropic>=0.40.0`). Пересборка venv тянет
свежие мажоры: на 03.09.2026 это дало `anthropic 1.3.0` (в 1.x — переезд на `httpx2`;
код проекта httpx напрямую не трогает, `messages.create` + `cache_control` не менялись).
При пересоздании venv — прогонять смоук: импорт агентов, `run_migrations()`, один LLM-вызов.

## Структура файлов
```
main.py                          — точка входа, wiring scheduler + bot
resume.md                        — резюме Denis (читается при старте, в системный промпт агентов)
pyrightconfig.json               — basedpyright (typeCheckingMode: standard)
requirements.txt                 — зависимости (ddgs, не duckduckgo-search); версии не запинены
railway.toml                     — рудимент от Railway, деплой давно на EC2; не используется
.github/workflows/deploy.yml     — GitHub Actions: auto-deploy on push to main
deploy/
  update.sh                      — ручное обновление бота на EC2 (fallback)
  job-hunt.service                — systemd unit для бота
  job-hunt-dashboard.service      — systemd unit для дашборда

src/config.py                    — Config dataclass (frozen), .env → единый источник истины
src/database/schema.py           — DDL + versioned migrations V1-V12 (run_migrations при старте)
src/database/repository.py       — VacancyRepository, CommunityEventRepository, паттерн Repository
src/event_utils.py               — is_past_event_date() — общий фильтр прошедших событий (DRY)

src/agents/base_agent.py         — BaseAgent: _chat() с prompt caching (cache_control: ephemeral)
src/agents/voice.py              — DENIS_VOICE (общий блок "голоса" для LetterAgent + OutreachAgent),
                                   extract_json_object(), has_dash() — см. архитектурные решения
src/agents/scout_agent.py        — ScoutAgent: pre-filter по title + LLM скоринг → ScoredVacancy
src/agents/research_agent.py     — ResearchAgent: ddgs (3 запроса) + LLM dossier
src/agents/letter_agent.py       — LetterAgent: письмо в стиле Denis (180-230 слов, без длинных тире,
                                   см. "Личность Denis"), принимает user_comments для перегенерации
src/agents/event_scout_agent.py  — EventScoutAgent: batch LLM скоринг tech-событий (category=professional)
src/agents/entertainment_scout_agent.py — EntertainmentScoutAgent: batch LLM скоринг досуговых событий Орхуса/Ютландии (category=entertainment)
src/agents/outreach_scout_agent.py — OutreachScoutAgent: batch LLM извлечение+классификация людей
                                     (tech_lead|hiring_manager|hr|other) из веб-поиска, confidence >= 6
src/agents/outreach_agent.py     — OutreachAgent: черновик LinkedIn connection-request note
                                   (200-260 симв., без тире, всегда отправляется Denis'ом вручную)

src/scrapers/base_scraper.py       — BaseScraper (ABC)
src/scrapers/jobindex_scraper.py   — Jobindex RSS, поиск по ключевым словам
src/scrapers/linkedin_scraper.py   — LinkedIn через cookie-auth (li_at + JSESSIONID)
src/scrapers/thehub_scraper.py     — The Hub REST API v2, главный датский tech job board
                                     (URL и description собираются отдельно — см. архитектурные решения)
src/scrapers/remotive_scraper.py   — Remotive public API, remote-only вакансии
src/scrapers/eventbrite_scraper.py — Eventbrite HTML → JSON-LD парсинг, без API ключа
src/scrapers/event_scraper.py      — ddgs поиск tech-событий
src/scrapers/entertainment_scraper.py — ddgs поиск развлекательных событий (концерты, фестивали, театр)
src/scrapers/outreach_finder.py    — поиск людей в компании: ddgs (site:linkedin.com/in) сначала,
                                     linkedin_api.search_people() как fallback

src/bot/telegram_bot.py          — весь Telegram UI (parse_mode="HTML" везде)
src/scheduler/jobs.py            — job functions: scout_jobindex, scout_remotive, scout_thehub,
                                   scout_linkedin, scout_events, scout_entertainment, run_research_for_vacancy

dashboard/api/main.py            — FastAPI app: run_migrations(), SPA catch-all, CORS, no docs
dashboard/api/pipeline.py        — run_research_pipeline(), regenerate_letter(),
                                   generate_company_report(), generate_match_analysis(),
                                   find_outreach_contacts(), draft_outreach_message()
dashboard/api/models.py          — Pydantic request/response models
dashboard/api/routers/
  vacancies.py                   — GET/PATCH /api/vacancies, PATCH /notes,
                                   POST generate-letter/regenerate-letter/company-report/match-analysis,
                                   POST find-outreach-contacts (vacancy-scoped, живёт здесь — см. решения)
  events.py                      — GET /api/events?category=, PATCH /api/events/{id}/status
  outreach.py                    — POST /api/outreach/{id}/draft-message, PATCH /{id}/status
                                   (contact-scoped, не влезает в /api/vacancies/{vacancy_id} префикс)
  stats.py                       — GET /api/stats
dashboard/frontend/              — React SPA (Vite build → dist/)
  src/api/client.ts              — axios с Basic Auth interceptors, AI_TIMEOUT=90000ms
  src/pages/VacanciesPage.tsx
  src/pages/VacancyDetailPage.tsx — статусы, action buttons (decoupled от генерации письма),
                                    AI reports, notes, status override, перегенерация письма с фидбеком,
                                    секция 🤝 Outreach contacts (find → draft → copy → mark sent)
  src/pages/EventsPage.tsx       — professional events (category=professional)
  src/pages/EntertainmentPage.tsx — развлекательные события (category=entertainment)
  src/pages/DashboardPage.tsx
  src/components/Navbar.tsx      — Dashboard | Vacancies | Events | 🎠 Entertainment
```

## База данных (SQLite)

### Таблица vacancies
```
id, source_id (UNIQUE), title, company, location, url, description,
posted_at, fetched_at, status, telegram_message_id,
platform, work_format, city,      ← V5, V6, V7
company_report,                   ← V9 (TEXT, NULL пока не сгенерирован)
match_analysis,                   ← V10 (TEXT, NULL пока не сгенерирован)
notes,                            ← V11 (TEXT, NULL — личные заметки Denis)
score                             ← V13 (INTEGER 1-10 от ScoutAgent, NULL для
                                     записей до миграции — бейдж в дашборде)
```
- `platform`: "jobindex" | "linkedin" | "thehub" | "remotive" | "unknown"
- `work_format`: "remote" | "hybrid" | "onsite" | "unknown"
- `source_id`: sha1(url) для Jobindex, "li_{job_id}" для LinkedIn, "thehub_{id}", "remotive_{id}"

### Таблица community_events (V8)
```
id, title, url (UNIQUE), event_type, location, event_date (ISO),
description, organizer, score, status, source, fetched_at, telegram_message_id,
category                          ← V12 ("professional" | "entertainment", DEFAULT 'professional')
```
- `status`: "new" | "interested" | "attending" | "attended" | "skipped"
- `source`: "eventbrite" | "web"
- `category`: "professional" (tech meetups) | "entertainment" (концерты, фестивали)

### Таблица outreach_contacts (V14)
```
id, vacancy_id (FK vacancies), company, full_name, headline,
role_category, linkedin_url (UNIQUE), source, message_draft,
status, fetched_at
```
- `role_category`: "tech_lead" | "hiring_manager" | "hr" | "other"
- `source`: "web" (ddgs) | "linkedin" (search_people fallback)
- `status`: "new" | "drafted" | "sent" | "replied" | "skipped"
- `linkedin_url` — дедупликация, как `source_id` у vacancies / `url` у events
- `sent` выставляет Denis вручную после того как сам отправил сообщение из LinkedIn —
  в таблице нет ничего похожего на "auto-sent" или timestamp автоотправки

### Статусы вакансий (полный жизненный цикл)
```
new → in_progress → letter_sent → applied → interview → offer → rejected → rejected_by_company
```
Дашборд: "in_progress" и "letter_sent" отображаются одинаково (внутренний статус).

### Миграции
V1-V4: таблицы vacancies, companies, cover_letters, events (аудит лог)
V5: platform, V6: work_format, V7: city
V8: community_events, V9: company_report, V10: match_analysis, V11: notes
V12: category в community_events (DEFAULT 'professional', существующие записи не затронуты)
V13: score в vacancies (INTEGER, NULL для существующих — скор не восстанавливается задним числом)
V14: outreach_contacts — люди для аутрича, найденные по конкретной вакансии
OCP: новые миграции только в конец `_MIGRATIONS` — старые не трогать.

## Расписание (CronTrigger, UTC)
```
06:00 UTC = 08:00 CEST  Jobindex
06:10 UTC = 08:10 CEST  Remotive
06:20 UTC = 08:20 CEST  The Hub
06:35 UTC = 08:35 CEST  LinkedIn      (медленнее — куки + get_job() на каждую вакансию)
07:10 UTC = 09:10 CEST  Events        (Eventbrite HTML + ddgs + LLM, category=professional)
07:30 UTC = 09:30 CEST  Entertainment (ddgs + LLM, category=entertainment, без Telegram)
```
Результаты готовы к 10:00 CEST. Ночной запуск не будит Denis.

## Telegram команды
```
/pending      — непросмотренные вакансии (status=new)
/done         — вакансии в работе (in_progress, letter_sent, applied, interview, offer)
/status       — статистика по всем статусам
/jobindex     — Jobindex вручную
/remotive     — Remotive вручную
/thehub       — The Hub вручную
/linkedin     — LinkedIn вручную
/events       — список событий из БД
/scout_events — запустить события вручную (Eventbrite + ddgs)
/attended     — отметить событие как посещённое
/help         — справка
```

## Дашборд (http://3.75.175.202:8080 или localhost:8080)
- HTTP Basic Auth (DASHBOARD_USER / DASHBOARD_PASSWORD)
- Вкладки: Dashboard, Vacancies, Events (professional), 🎠 Entertainment
- Фильтры по статусу; события фильтруются по category на уровне API
- VacanciesPage (список): колонка со скором (score, V13 — зелёный/жёлтый/красный бейдж)
  и inline кнопка ❌ Reject в каждой строке (stopPropagation, мгновенно, без перезагрузки страницы)
- Events и Entertainment — карточки с inline кнопками смены статуса (new/interested/attending/attended/skipped)
- Детальная карточка вакансии:
  - **Action bar**: `⚙️ Take to work` (мгновенно, только статус) · `📤 Mark applied` · `❌ Reject` и т.д.
  - **✉️ Cover letter секция**: кнопка `✨ Generate cover letter` (AI pipeline ~20 сек) — отдельно от action bar
  - `✏️ Regenerate with feedback` — перегенерация с комментарием
  - "📝 My notes" — textarea для личных заметок (PATCH /notes, хранится в БД V11)
  - Job description (HTML или plain text через descriptionToHtml())
  - Версионирование писем: v1, v2, v3... — история итераций в БД
  - **🤝 Outreach contacts секция**: `🔍 Find contacts` (ddgs + LinkedIn fallback) → карточка на
    человека (имя, роль, ссылка на LinkedIn) → `✍️ Draft message` → редактируемый textarea →
    `📋 Copy` → Denis сам отправляет из LinkedIn → `✅ Mark sent`. Никакой автоотправки нигде в UI.
- AI секции (кэшированы в БД V9/V10):
  - "Company report" — 3 ddgs запроса + LLM (max_tokens=1400)
  - "Match analysis" — сравнение резюме с вакансией (max_tokens=1200)
- Кнопка "🔄 Regenerate" обнуляет кэш и показывает кнопку генерации

## Поток данных (вакансии)
```
scraper.fetch()
  → pre-filter по title (_is_tech_title) — без LLM, бесплатно
  → [LinkedIn only] get_job() для прошедших фильтр (company, location, description)
  → ScoutAgent.run() → LLM скоринг → ScoredVacancy(vacancy, score, reason, work_format, stack)
  → VacancyRepository.upsert() → (id, is_new)
  → is_new=True → notify_vacancy() в Telegram
  → Denis: [✅ В работу] → status=in_progress (мгновенно, без AI)
  → Denis: [✨ Generate cover letter] → run_research_pipeline()
    → ResearchAgent (ddgs + LLM) → Company dossier
    → LetterAgent (resume + dossier + job desc) → CoverLetter → status=letter_sent
  → Denis: [📤 Mark applied] → status=applied (независимо от наличия письма)
```

## Поток данных (профессиональные события)
```
EventbriteScraper.fetch() → list[CommunityEvent] (JSON-LD из HTML, score по локации)
  → is_past_event_date() hard filter — прошедшие отсекаются до LLM
EventScraper.fetch()      → list[dict] (ddgs snippets)
  → EventScoutAgent.run(today=date.today()) → list[ScoredEvent]
     — today в user-промпте, is_past_event_date() в коде (defense in depth)
     — score >= 5 → category='professional'
CommunityEventRepository.upsert() → (id, is_new)
  → is_new=True → notify_event() в Telegram
Denis: кнопки смены статуса на дашборде или в Telegram
```

## Поток данных (развлекательные события)
```
EntertainmentScraper.fetch() → list[dict] (ddgs: концерты, фестивали, театр Орхус/Ютландия)
  → EntertainmentScoutAgent.run(today=date.today()) → list[ScoredEvent]
     — today в user-промпте, is_past_event_date() в коде
     — score >= 5 → category='entertainment'
     — max_tokens=2500 (8 запросов дают ~60 результатов)
CommunityEventRepository.upsert() → (id, is_new)
  → Telegram уведомлений НЕТ — только дашборд
Denis: кнопки смены статуса на странице Entertainment
```

## Поток данных (outreach)
```
Denis на карточке вакансии: [🔍 Find contacts]
  → OutreachFinder.find(company): ddgs (site:linkedin.com/in, 2 группы запросов по ролям)
     → если пусто: linkedin_api.search_people() fallback, ТОЛЬКО тогда, один раз
  → OutreachScoutAgent.run(): один batch LLM вызов, строгая фильтрация по confidence >= 6
     (ddgs отдаёт много шума — несвязанные люди, старые позиции; модель должна отклонять
     всё что не явно "сейчас работает в этой компании, в релевантной роли")
  → OutreachContactRepository.upsert() → (id, is_new), дедуп по linkedin_url
Denis на карточке контакта: [✍️ Draft message]
  → OutreachAgent.run(contact, vacancy) → LinkedIn connection-request note, 200-260 симв.
  → save_message_draft() → status='drafted'
Denis: редактирует в textarea (если нужно) → [📋 Copy] → вставляет и отправляет САМ из LinkedIn
  → [✅ Mark sent] → status='sent' (ничего не отправляется системой автоматически)
```

## Ключевые архитектурные решения

### Асинхронность
Все blocking вызовы (scrapers, agents, sqlite) — через `asyncio.to_thread()`.
Event loop не блокируется — Telegram polling работает непрерывно.

### Дедупликация
`upsert()` возвращает `(id, is_new)`. Уведомление только при `is_new=True`.
`UNIQUE` constraint на `source_id` (вакансии) и `url` (события).

### Pre-filter перед LLM
`_is_tech_title()` в scout_agent.py фильтрует нетехнические вакансии до вызова Claude.
LinkedIn: `get_job()` вызывается только для прошедших title-фильтр.
Экономия ~80% токенов на скоринге.

### Scout — location hard filter
ScoutAgent применяет location rules ДО скоринга по стеку.
Reject: onsite/hybrid вне Дании; remote с любым региональным ограничением (EU, EMEA, Europe, US, UK, и т.д.).
Accept: только Дания (любой формат) ИЛИ remote без какого-либо географического ограничения (worldwide/global/не указано).
"If in doubt — reject" — явная инструкция в промпте.
Rejected вакансии получают score=2, relevant=false — не доходят до уведомления.

### Events — hard date filter
`src/event_utils.py::is_past_event_date(event_date, today)` — общая утилита (DRY).
Применяется в: EventbriteScraper.fetch(), EventScoutAgent.run(), EntertainmentScoutAgent.run().
today передаётся в user-промпт агентам явно (system prompt кэшируется, нельзя нести дату).
Defense in depth: и LLM инструктирован отклонять прошедшие, и код перепроверяет.
Неизвестная дата (None) — не отклоняется (нет данных ≠ прошедшее).

### Категории событий (V12)
community_events.category = 'professional' | 'entertainment'.
Один репозиторий, один API endpoint — фильтрация через ?category= query param.
`get_all_by_statuses(statuses, category=None)` — category=None возвращает все.
Entertainment job НЕ шлёт Telegram уведомления — только сохраняет в БД для дашборда.

### Description хранение
Scrapers хранят description без обрезки ([:2000] убран).
ScoutAgent сам урезает до [:800] только для своего LLM-вызова.
Frontend: descriptionToHtml() — если нет HTML-тегов (LinkedIn, Remotive) → конвертирует \n\n в <p>.

### LetterAgent — decoupled от Take to work
`⚙️ Take to work` → только `updateVacancyStatus(id, 'in_progress')` (мгновенно).
`✨ Generate cover letter` — отдельная кнопка в секции письма, вызывает AI pipeline (~20 сек).
Можно нажать `📤 Mark applied` без генерации письма — ничего не блокирует.
Паттерн идентичен Company report и Match analysis секциям (SRP).

### LetterAgent — перегенерация с фидбеком
`LetterAgent.run(vacancy, company, user_comments)` — user_comments добавляется в промпт.
`pipeline.regenerate_letter(vacancy_id, comments)` — без повторного research.
Версионирование: каждая перегенерация сохраняется как v2, v3 и т.д. — история остаётся в БД.

### Prompt caching
`BaseAgent._chat()` кэширует system prompt через `cache_control: ephemeral`.
System prompt (с полным текстом резюме) строится один раз в `__init__` агента.
Дата (today) передаётся в user-промпт, а не в system prompt — иначе кэш инвалидируется каждый день.

### EventScoutAgent / EntertainmentScoutAgent — batch vs per-item
Один LLM вызов на весь batch событий (не per-item как ScoutAgent).
Дешевле: события менее важны чем вакансии, точность допустимо ниже.
`_strip_markdown()`: использует `find('{')` / `rfind('}')` для извлечения JSON —
надёжнее чем regex `{.*?}` который останавливается на первой `}` во вложенном объекте.

### AI reports кэш в БД
company_report и match_analysis хранятся в DB (V9, V10).
Дашборд загружает их при открытии карточки — токены не тратятся при повторных открытиях.
"🔄 Regenerate" обнуляет поле в state (не в DB) → показывает кнопку → новый POST → сохраняет в DB.

### Dashboard SPA routing
`dashboard/api/main.py`: `/assets` монтируется как StaticFiles (JS/CSS с cache headers).
Catch-all `/{full_path:path}` → `FileResponse(index.html)` — для browser refresh на /vacancies/42 и т.д.
`StaticFiles(html=True)` на "/" НЕ работает для SPA — ищет файл буквально по пути.

### Dashboard auth
`secrets.compare_digest()` — защита от timing attacks.
Credentials в sessionStorage браузера — сбрасываются при закрытии вкладки.
`verifyCredentials()` использует чистый axios (без interceptors) для проверки при логине —
иначе 401 interceptor вызвал бы reload до того как catch покажет ошибку.

### OCP на скраперах
Новый scraper = новый класс, наследующий `BaseScraper`.
Существующий код не меняется (jobs.py получает новый scraper через import + add_job).

### Outreach — LinkedIn draft-only, без автоотправки (14.09.2026)
`linkedin_api` (уже зависимость проекта, уже используется для job scraping) технически умеет
`search_people`, `get_profile`, `add_connection`, `send_message` — полная автоматизация
возможна. Осознанно не делаем: LinkedIn Automation Policy явно запрещает скриптовую отправку
сообщений/коннектов, и это активно детектится. Текущее использование (job scraping через
cookie-auth) — уже серая зона, которую Denis принимает; автоотправка с личного аккаунта —
принципиально другой уровень риска: ограничение аккаунта ударит прямо во время активного
поиска работы, это хуже чем потерять один источник вакансий.
Решение: система находит людей и готовит черновик, Denis копирует и отправляет сам из
LinkedIn UI. Нигде в коде нет вызова `send_message()` или `add_connection()`.
Источники контактов: ddgs (публичный веб-поиск, не трогает LinkedIn-сессию) сначала,
`search_people()` — fallback, и только один раз за клик "Find contacts" (не по расписанию,
не батчами) — активность на LinkedIn остаётся низкой и человеческого темпа.

### DENIS_VOICE — общий модуль "голоса" (DRY)
`src/agents/voice.py` — блок "кто такой Denis" + запрет тире, вынесен из letter_agent.py при
добавлении OutreachAgent (14.09.2026): оба агента должны звучать как один и тот же человек,
дублировать промпт-текст в двух местах значило бы настраивать тон дважды при каждой правке.
Также здесь `extract_json_object()` (find/rfind вместо non-greedy regex — тот же fix что был
в `_strip_markdown()` у event/entertainment scout агентов, теперь общий, не третья копия).

**has_dash() — defense in depth против тире.** Инструкция "никогда не используй тире" не
гарантирует соблюдение: при разработке OutreachAgent модель скопировала en dash (–) прямо
из заголовка вакансии ("Software Engineer – Integrations"), который был в промпте как
контекст — а отдельно, на чистых данных без источника с тире, всё равно иногда вставляла
свой em dash в качестве риторической конструкции (~1 из 3 прогонов). Код теперь перепроверяет
результат и делает один retry с явным указанием на конкретную ошибку — тот же принцип, что
`is_past_event_date()` (инструкция LLM + проверка в коде). Применено и в LetterAgent, и в
OutreachAgent. Важно: правило должно запрещать сам символ (— или –), а не только em dash —
исходная формулировка называла оба, но приводила только символ em dash как пример, из-за
чего en dash из чужого текста проходил незамеченным.

### TheHub — миграция на API v2 (04.09.2026)
`https://thehub.io/api/jobs` стал отдавать 404 — TheHub перевёл поиск на `/api/v2/jobs`
без анонса. Обнаружено потому что вакансии с TheHub перестали приходить (бот молчал 2 месяца,
за это время API успел смениться). Форма ответа `docs[]` та же, но пропали `absoluteJobUrl`
и `description`:
- URL строится вручную из `id`: `https://thehub.io/jobs/{id}` (проверено по ссылкам на
  странице листинга)
- `description` берётся отдельным запросом на страницу вакансии — там есть JSON-LD
  (`schema.org JobPosting`), тем же приёмом, что `EventbriteScraper` использует для событий
- Enrichment идёт только для вакансий, прошедших `_is_tech_title()` — паттерн как в
  `LinkedInScraper._enrich_descriptions()`, не тратим лишние запросы на заведомо нерелевантные
- Порядок атрибутов в `<script>`-теге на странице TheHub нестандартный (`data-hid` перед
  `type`) — regex не завязан на порядок, матчит любой `ld+json` блок и проверяет `@type`
  после `json.loads()`

Урок: сторонние API job board'ов меняются без уведомления. Если вакансии с площадки резко
пропали (0 fetched в логах при том что раньше были), первым делом проверять код ответа
скрапера напрямую (`curl`), а не сразу чинить логику скоринга.

### FIX: dashboard/api/pipeline.py использовал старое имя пакета (14.09.2026)
`from duckduckgo_search import DDGS` вместо `from ddgs import DDGS` — единственное место в
проекте с таким импортом, всё остальное давно на `ddgs`. Ловилось `ModuleNotFoundError` при
любом вызове функций из pipeline.py, включая кнопку "Company report" на дашборде — она была
сломана в проде необнаруженным. Обнаружено попутно при добавлении outreach-функций в тот же
файл: `find_outreach_contacts()` не заработала бы, не почини строку импорта.

## .env переменные
```
ANTHROPIC_API_KEY
ANTHROPIC_MODEL=claude-sonnet-4-6
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=118955139
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

## Личность Denis (для letter_agent)
Открытый, тёплый, эмпат. Интроверт который хорошо общается (энергия тратится).
Юмор сухой и сдержанный, ближе к датскому, чем к американскому — deadpan, без форсированных
шуток. Живёт в Aarhus достаточно долго, чтобы иметь мнение про плоские иерархии и датскую
прямоту — но это фон, не повторяющаяся шутка в каждом письме. YouTube канал @midlifecode
(1300+ подп.) — упоминается по ситуации, не как дежурный факт. Открыт к переезду куда угодно —
без драмы, прямо, не извиняющимся тоном ("happy to relocate", не "would need some conversation").
Запоминающийся, яркий. Письма должны звучать как реальное сообщение человеку, а не как
эссе, написанное чтобы впечатлить.

**04.09.2026 — переписан промпт (`src/agents/letter_agent.py`).** Раньше LetterAgent генерировал
формально-правильные, но "ИИ-шные" письма: 250-320 слов, обильные длинные тире, конструкции
"It's not X, it's Y", пересказ 2-3 компаний из резюме подряд, одинаковая шаблонная концовка
про work permit/Aarhus/YouTube в каждом письме. Абстрактная инструкция "dry wit" в промпте
не работала — юмора не было вообще. Что изменилось:
- **Длинные тире запрещены явно** — прямое требование Denis: это главный маркер ИИ-текста
  (совпадает с его глобальным CLAUDE.md-правилом про форматирование, но здесь применено
  к тексту, который генерирует LLM, а не к моим собственным ответам)
- Длина сокращена до 180-230 слов (было 250-320)
- В промпт добавлен список конкретных наблюдаемых штампов как "avoid" — абстрактные
  инструкции про тон не работают, конкретные примеры плохих оборотов работают
- Переезд: раньше "упоминать только при неоднозначности локации" → теперь прямо и уверенно,
  раз Denis реально готов переехать куда угодно

## Что не реализовано (возможные следующие шаги)
- Indeed scraper
- Greenhouse/Lever API для карьерных страниц компаний
- Meetup RSS (нет без Pro подписки)
- Dashboard stats разбить по категориям событий (сейчас events считаются все вместе)
- Email outreach (осознанно отложено — поиск личных email адресов людей заметно более
  GDPR-чувствителен чем поиск публичных LinkedIn-профилей через ddgs; решать отдельно,
  если LinkedIn draft-flow окажется полезным)
- Telegram-уведомления для outreach (сейчас только дашборд, по прецеденту Entertainment —
  добавить notify_* тривиально, если понадобятся push-уведомления о новых контактах)
- Standalone outreach по компании без привязанной вакансии (сейчас всегда стартует от
  вакансии — есть контекст для персонализации сообщения)
