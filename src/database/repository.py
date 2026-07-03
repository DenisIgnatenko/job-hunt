"""
Repository pattern (SRP + DIP): all data access in one place.
Agents and scrapers depend on this abstraction, not on SQLite directly.
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional

from src.database.schema import get_connection


# --- Data transfer objects -----------------------------------------------

@dataclass
class Vacancy:
    source_id: str
    title: str
    url: str
    company: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[str] = None
    status: str = "new"
    platform: str = "unknown"
    work_format: str = "unknown"
    score: Optional[int] = None            # ScoutAgent score 1-10 (V13)
    id: Optional[int] = None
    fetched_at: Optional[str] = None
    telegram_message_id: Optional[int] = None
    company_report: Optional[str] = None   # AI отчёт о компании (кэш)
    match_analysis: Optional[str] = None   # AI анализ совпадения с резюме (кэш)
    notes: Optional[str] = None            # личные заметки Denis


@dataclass
class Company:
    name: str
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    summary: Optional[str] = None
    researched_at: Optional[str] = None
    id: Optional[int] = None


@dataclass
class CoverLetter:
    vacancy_id: int
    body: str
    version: int = 1
    approved: bool = False
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class CommunityEvent:
    title: str
    url: str
    event_type: str = "other"       # meetup | conference | workshop | hackathon | other
    location: Optional[str] = None
    event_date: Optional[str] = None  # ISO date "YYYY-MM-DD", None if unknown
    description: Optional[str] = None
    organizer: Optional[str] = None
    score: int = 0                  # relevance score 1-10 from LLM
    status: str = "new"             # new | interested | attending | attended | skipped
    source: str = "web"             # web | meetup | eventbrite
    category: str = "professional"  # professional | entertainment (V12)
    id: Optional[int] = None
    fetched_at: Optional[str] = None
    telegram_message_id: Optional[int] = None


# --- VacancyRepository ---------------------------------------------------

class VacancyRepository:

    def upsert(self, vacancy: Vacancy) -> tuple[int, bool]:
        """Insert or ignore duplicate (by source_id).
        Returns (id, is_new): is_new=True only on first insert.
        """
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO vacancies (source_id, title, company, location, city, url,
                                       description, posted_at, status, platform, work_format)
                VALUES (:source_id, :title, :company, :location, :city, :url,
                        :description, :posted_at, :status, :platform, :work_format)
                ON CONFLICT(source_id) DO NOTHING
                """,
                {
                    "source_id": vacancy.source_id,
                    "title": vacancy.title,
                    "company": vacancy.company,
                    "location": vacancy.location,
                    "city": vacancy.city,
                    "url": vacancy.url,
                    "description": vacancy.description,
                    "posted_at": vacancy.posted_at,
                    "status": vacancy.status,
                    "platform": vacancy.platform,
                    "work_format": vacancy.work_format,
                },
            )
            conn.commit()
            if cur.lastrowid:
                return cur.lastrowid, True  # newly inserted
            row = conn.execute(
                "SELECT id FROM vacancies WHERE source_id = ?", (vacancy.source_id,)
            ).fetchone()
            return row["id"], False  # already existed

    def get_by_id(self, vacancy_id: int) -> Optional[Vacancy]:
        """FIX: added — required by research pipeline triggered from Telegram callback."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)
            ).fetchone()
        return _row_to_vacancy(row) if row else None

    def get_by_status(self, status: str) -> list[Vacancy]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM vacancies WHERE status = ? ORDER BY fetched_at DESC",
                (status,),
            ).fetchall()
        return [_row_to_vacancy(r) for r in rows]

    def search(self, q: str, limit: int = 200) -> list["Vacancy"]:
        pattern = f"%{q}%"
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM vacancies
                   WHERE title LIKE ? OR company LIKE ? OR location LIKE ?
                   ORDER BY fetched_at DESC LIMIT ?""",
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [_row_to_vacancy(r) for r in rows]

    def get_all_by_statuses(self, statuses: list[str]) -> list["Vacancy"]:
        placeholders = ",".join("?" * len(statuses))
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM vacancies WHERE status IN ({placeholders}) ORDER BY fetched_at DESC",
                statuses,
            ).fetchall()
        return [_row_to_vacancy(r) for r in rows]

    def update_status(self, vacancy_id: int, status: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE vacancies SET status = ? WHERE id = ?", (status, vacancy_id)
            )
            conn.commit()

    def update_score(self, vacancy_id: int, score: int) -> None:
        """Сохраняет ScoutAgent score — вызывается в _run_scout() после upsert."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE vacancies SET score = ? WHERE id = ?",
                (score, vacancy_id),
            )
            conn.commit()

    def save_company_report(self, vacancy_id: int, report: str) -> None:
        """Сохраняет AI отчёт о компании — вызывается из dashboard pipeline."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE vacancies SET company_report = ? WHERE id = ?",
                (report, vacancy_id),
            )
            conn.commit()

    def save_notes(self, vacancy_id: int, notes: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE vacancies SET notes = ? WHERE id = ?",
                (notes, vacancy_id),
            )
            conn.commit()

    def save_match_analysis(self, vacancy_id: int, analysis: str) -> None:
        """Сохраняет AI анализ совпадения с резюме — вызывается из dashboard pipeline."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE vacancies SET match_analysis = ? WHERE id = ?",
                (analysis, vacancy_id),
            )
            conn.commit()

    def save_telegram_message_id(self, vacancy_id: int, message_id: int) -> None:
        """
        FIX: added — stores Telegram message ID so callback handler can
        edit the original message (show ✅/❌) instead of sending a new one.
        Called immediately after bot.send_message() in notify_vacancy().
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE vacancies SET telegram_message_id = ? WHERE id = ?",
                (message_id, vacancy_id),
            )
            conn.commit()


# --- CompanyRepository ---------------------------------------------------

class CompanyRepository:

    def upsert(self, company: Company) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO companies (name, website, linkedin_url, summary, researched_at)
                VALUES (:name, :website, :linkedin_url, :summary, :researched_at)
                ON CONFLICT(name) DO UPDATE SET
                    website       = excluded.website,
                    linkedin_url  = excluded.linkedin_url,
                    summary       = excluded.summary,
                    researched_at = excluded.researched_at
                """,
                {
                    "name": company.name,
                    "website": company.website,
                    "linkedin_url": company.linkedin_url,
                    "summary": company.summary,
                    "researched_at": company.researched_at,
                },
            )
            conn.commit()
            if cur.lastrowid:
                return cur.lastrowid
            row = conn.execute(
                "SELECT id FROM companies WHERE name = ?", (company.name,)
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Company '{company.name}' not found after upsert")
            return row["id"]

    def get_by_name(self, name: str) -> Optional[Company]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE name = ?", (name,)
            ).fetchone()
        return _row_to_company(row) if row else None


# --- CoverLetterRepository -----------------------------------------------

class CoverLetterRepository:

    def save(self, letter: CoverLetter) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO cover_letters (vacancy_id, body, version, approved)
                VALUES (:vacancy_id, :body, :version, :approved)
                """,
                {
                    "vacancy_id": letter.vacancy_id,
                    "body": letter.body,
                    "version": letter.version,
                    "approved": int(letter.approved),
                },
            )
            conn.commit()
            if cur.lastrowid is None:
                raise RuntimeError("INSERT cover_letters did not return a row ID")
            return cur.lastrowid

    def approve(self, letter_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE cover_letters SET approved = 1 WHERE id = ?", (letter_id,)
            )
            conn.commit()

    def get_vacancy_id_by_letter(self, letter_id: int) -> Optional[int]:
        """Returns vacancy_id for a given letter_id. Used by Telegram callback after approval."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT vacancy_id FROM cover_letters WHERE id = ?", (letter_id,)
            ).fetchone()
        return row["vacancy_id"] if row else None

    def get_by_vacancy(self, vacancy_id: int) -> list[CoverLetter]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cover_letters WHERE vacancy_id = ? ORDER BY version DESC",
                (vacancy_id,),
            ).fetchall()
        return [_row_to_letter(r) for r in rows]


# --- CommunityEventRepository --------------------------------------------

class CommunityEventRepository:

    def get_by_id(self, event_id: int) -> Optional[CommunityEvent]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM community_events WHERE id = ?", (event_id,)
            ).fetchone()
        return _row_to_event(row) if row else None

    def upsert(self, event: CommunityEvent) -> tuple[int, bool]:
        """Insert or ignore duplicate (by url). Returns (id, is_new)."""
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO community_events
                    (title, url, event_type, location, event_date,
                     description, organizer, score, status, source, category)
                VALUES
                    (:title, :url, :event_type, :location, :event_date,
                     :description, :organizer, :score, :status, :source, :category)
                ON CONFLICT(url) DO NOTHING
                """,
                {
                    "title":       event.title,
                    "url":         event.url,
                    "event_type":  event.event_type,
                    "location":    event.location,
                    "event_date":  event.event_date,
                    "description": event.description,
                    "organizer":   event.organizer,
                    "score":       event.score,
                    "status":      event.status,
                    "source":      event.source,
                    "category":    event.category,
                },
            )
            conn.commit()
            if cur.lastrowid:
                return cur.lastrowid, True
            row = conn.execute(
                "SELECT id FROM community_events WHERE url = ?", (event.url,)
            ).fetchone()
            return row["id"], False

    def get_all_by_statuses(
        self,
        statuses: list[str],
        category: Optional[str] = None,
    ) -> list[CommunityEvent]:
        """Возвращает события по статусам. category=None — все категории (DIP: не зависим от конкретной)."""
        placeholders = ",".join("?" * len(statuses))
        params: list = list(statuses)
        category_clause = ""
        if category:
            category_clause = " AND category = ?"
            params.append(category)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM community_events WHERE status IN ({placeholders})"
                f"{category_clause}"
                f" ORDER BY event_date ASC, fetched_at DESC",
                params,
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def update_status(self, event_id: int, status: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE community_events SET status = ? WHERE id = ?", (status, event_id)
            )
            conn.commit()

    def save_telegram_message_id(self, event_id: int, message_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE community_events SET telegram_message_id = ? WHERE id = ?",
                (message_id, event_id),
            )
            conn.commit()


# --- Helpers -------------------------------------------------------------

def _row_to_vacancy(row: sqlite3.Row) -> Vacancy:
    d = dict(row)
    # Only pass fields that Vacancy dataclass knows about
    known = {k for k in Vacancy.__dataclass_fields__}
    return Vacancy(**{k: v for k, v in d.items() if k in known})


def _row_to_company(row: sqlite3.Row) -> Company:
    d = dict(row)
    known = {k for k in Company.__dataclass_fields__}
    return Company(**{k: v for k, v in d.items() if k in known})


def _row_to_letter(row: sqlite3.Row) -> CoverLetter:
    d = dict(row)
    d["approved"] = bool(d["approved"])
    known = {k for k in CoverLetter.__dataclass_fields__}
    return CoverLetter(**{k: v for k, v in d.items() if k in known})


def _row_to_event(row: sqlite3.Row) -> CommunityEvent:
    d = dict(row)
    known = {k for k in CommunityEvent.__dataclass_fields__}
    return CommunityEvent(**{k: v for k, v in d.items() if k in known})
