"""
Single source of truth for all configuration (SRP + DRY).
All values come from environment variables via .env file.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class Config:
    # Anthropic
    anthropic_api_key: str
    anthropic_model: str

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: int  # FIX: must be int — python-telegram-bot requires int, str causes silent failures

    # Database
    database_url: str

    # Scheduler
    scout_interval_hours: int
    research_interval_hours: int

    # Jobindex scraper
    jobindex_rss_url: str
    jobindex_keywords: list[str]
    jobindex_location: str

    # LinkedIn scraper
    linkedin_email: str
    linkedin_password: str
    linkedin_cookie: str         # li_at cookie — preferred over email/password
    linkedin_jsessionid: str     # JSESSIONID cookie — required alongside li_at
    linkedin_interval_hours: int

    # Dashboard — HTTP Basic Auth
    dashboard_user: str
    dashboard_password: str

    # Resume — loaded once at startup, injected into all agents
    resume_text: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            anthropic_api_key=_require("ANTHROPIC_API_KEY"),
            # FIX: claude-sonnet-4-6 as default — opus is 15x more expensive,
            # not justified for vacancy scoring with max_tokens=256.
            # Use ANTHROPIC_MODEL=claude-opus-4-6 in .env only if needed.
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            # FIX: cast to int — Telegram chat IDs are integers
            telegram_chat_id=int(_require("TELEGRAM_CHAT_ID")),
            database_url=os.getenv("DATABASE_URL", "sqlite:///job_hunt.db"),
            scout_interval_hours=int(os.getenv("SCOUT_INTERVAL_HOURS", "6")),
            research_interval_hours=int(os.getenv("RESEARCH_INTERVAL_HOURS", "1")),
            jobindex_rss_url=os.getenv(
                "JOBINDEX_RSS_URL",
                "https://www.jobindex.dk/jobsoegning.rss",
            ),
            jobindex_keywords=_split_list(os.getenv(
                "JOBINDEX_KEYWORDS",
                # FIX: Denis's actual target keywords — Java, Go, Node.js, TypeScript
                # Previously empty string → scraper fetched nothing
                "Java developer,Go developer,Golang,Node.js backend,Spring Boot,Fullstack developer,Backend engineer,Softwareudvikler",
            )),
            jobindex_location=os.getenv("JOBINDEX_LOCATION", ""),
            linkedin_email=os.getenv("LINKEDIN_EMAIL", ""),
            linkedin_password=os.getenv("LINKEDIN_PASSWORD", ""),
            linkedin_cookie=os.getenv("LINKEDIN_COOKIE", ""),
            linkedin_jsessionid=os.getenv("LINKEDIN_JSESSIONID", ""),
            linkedin_interval_hours=int(os.getenv("LINKEDIN_INTERVAL_HOURS", "12")),
            dashboard_user=os.getenv("DASHBOARD_USER", "denis"),
            dashboard_password=os.getenv("DASHBOARD_PASSWORD", "changeme"),
            resume_text=_load_resume(),
        )


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return value


def _split_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _load_resume() -> str:
    path = Path(os.getenv("RESUME_PATH", str(_PROJECT_ROOT / "resume.md")))
    if not path.exists():
        raise FileNotFoundError(
            f"Resume file not found: {path}. "
            "Set RESUME_PATH in .env or place resume.md in project root."
        )
    return path.read_text(encoding="utf-8")


# Module-level singleton — import config directly where needed.
config = Config.from_env()
