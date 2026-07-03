"""
DDL definitions and migration runner (SRP: schema ownership lives here).
Uses SQLite via sqlite3 stdlib — no ORM dependency in schema layer.

Migration strategy: versioned migrations table.
Each migration runs exactly once, identified by version number.
Safe to re-run run_migrations() on every startup.
"""

import sqlite3
from pathlib import Path

from src.config import config


# --- DDL -----------------------------------------------------------------

_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# v1 — initial schema
# FIX: expanded status set to support full HITL lifecycle.
# Previous: ('new','researched','applied','rejected','offer') — missing Denis approval steps.
# Now: vacancy goes through Denis's explicit decisions at each stage.
_V1_VACANCIES = """
CREATE TABLE IF NOT EXISTS vacancies (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id            TEXT    NOT NULL UNIQUE,
    title                TEXT    NOT NULL,
    company              TEXT,
    location             TEXT,
    url                  TEXT    NOT NULL,
    description          TEXT,
    posted_at            TEXT,
    fetched_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    status               TEXT    NOT NULL DEFAULT 'new'
                         CHECK(status IN (
                             'new',                 -- found by scraper, scored by Scout
                             'in_progress',         -- Denis clicked "В работу", pipeline running
                             'letter_sent',         -- letter generated and sent to Denis
                             'applied',             -- Denis submitted the application
                             'interview',           -- interview scheduled
                             'offer',               -- offer received
                             'rejected',            -- Denis skipped
                             'rejected_by_company'  -- company said no
                         )),
    telegram_message_id  INTEGER
);
"""

_V1_COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    website       TEXT,
    linkedin_url  TEXT,
    summary       TEXT,
    researched_at TEXT
);
"""

_V1_COVER_LETTERS = """
CREATE TABLE IF NOT EXISTS cover_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id  INTEGER NOT NULL REFERENCES vacancies(id),
    body        TEXT    NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    approved    INTEGER NOT NULL DEFAULT 0
);
"""

_V1_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    entity     TEXT    NOT NULL,
    entity_id  INTEGER NOT NULL,
    event      TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_V5_ADD_META_FIELDS = """
ALTER TABLE vacancies ADD COLUMN platform    TEXT NOT NULL DEFAULT 'unknown';
"""
_V6_ADD_WORK_FORMAT = """
ALTER TABLE vacancies ADD COLUMN work_format TEXT NOT NULL DEFAULT 'unknown';
"""
_V7_ADD_CITY = """
ALTER TABLE vacancies ADD COLUMN city TEXT;
"""

# V8 — community events (meetups, conferences, workshops).
# Named community_events to avoid conflict with V4 audit-log events table.
_V8_COMMUNITY_EVENTS = """
CREATE TABLE IF NOT EXISTS community_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT    NOT NULL,
    url                 TEXT    NOT NULL UNIQUE,
    event_type          TEXT    NOT NULL DEFAULT 'other',
    location            TEXT,
    event_date          TEXT,           -- ISO date YYYY-MM-DD, NULL if unknown
    description         TEXT,
    organizer           TEXT,
    score               INTEGER NOT NULL DEFAULT 0,
    status              TEXT    NOT NULL DEFAULT 'new'
                        CHECK(status IN (
                            'new',         -- found, not yet shown to Denis
                            'interested',  -- Denis clicked "Интересно"
                            'attending',   -- Denis confirmed attendance
                            'attended',    -- Denis was there
                            'skipped'      -- Denis skipped
                        )),
    source              TEXT    NOT NULL DEFAULT 'web',
    fetched_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    telegram_message_id INTEGER
);
"""

# V9/V10 — AI reports кэшируются в БД чтобы не тратить токены при повторном открытии.
# conn.execute() принимает только одно выражение — два ALTER = два migration.
_V9_ADD_COMPANY_REPORT = """
ALTER TABLE vacancies ADD COLUMN company_report TEXT;
"""
_V10_ADD_MATCH_ANALYSIS = """
ALTER TABLE vacancies ADD COLUMN match_analysis TEXT;
"""
_V11_ADD_NOTES = """
ALTER TABLE vacancies ADD COLUMN notes TEXT;
"""

# V12 — категория события: professional (tech-meetups) | entertainment (досуг).
# Дефолт 'professional' — все существующие записи остаются в своей категории без изменений.
_V12_ADD_EVENT_CATEGORY = """
ALTER TABLE community_events ADD COLUMN category TEXT NOT NULL DEFAULT 'professional';
"""

# V13 — ScoutAgent score (1-10) сохраняется в БД чтобы показывать в дашборде.
# NULL для вакансий, добавленных до этой миграции.
_V13_ADD_VACANCY_SCORE = """
ALTER TABLE vacancies ADD COLUMN score INTEGER;
"""

# Versioned migration list.
# OCP: add new migrations at the end — never modify existing entries.
# Each tuple: (version: int, sql: str)
_MIGRATIONS: list[tuple[int, str]] = [
    (1, _V1_VACANCIES),
    (2, _V1_COMPANIES),
    (3, _V1_COVER_LETTERS),
    (4, _V1_EVENTS),
    (5, _V5_ADD_META_FIELDS),
    (6, _V6_ADD_WORK_FORMAT),
    (7, _V7_ADD_CITY),
    (8, _V8_COMMUNITY_EVENTS),
    (9, _V9_ADD_COMPANY_REPORT),
    (10, _V10_ADD_MATCH_ANALYSIS),
    (11, _V11_ADD_NOTES),
    (12, _V12_ADD_EVENT_CATEGORY),
    (13, _V13_ADD_VACANCY_SCORE),
]


# --- Runner --------------------------------------------------------------

def _db_path() -> Path:
    url = config.database_url
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return Path(url)


def run_migrations() -> None:
    """
    Apply all pending migrations in order.
    Idempotent — safe to call on every startup.
    Already-applied migrations are skipped via schema_migrations table.
    """
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(_CREATE_MIGRATIONS_TABLE)
        conn.commit()

        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for version, ddl in _MIGRATIONS:
            if version in applied:
                continue
            conn.execute(ddl)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            conn.commit()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
