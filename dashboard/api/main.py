"""
FastAPI дашборд (SRP: отдельный процесс, читает ту же SQLite что и бот).
Порт 8080. Аутентификация: HTTP Basic Auth (DASHBOARD_USER / DASHBOARD_PASSWORD).

Запуск локально:
  uvicorn dashboard.api.main:app --reload --port 8080

На EC2 запускается как отдельный systemd сервис job-hunt-dashboard.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dashboard.api.routers import events, stats, vacancies
from src.database.schema import run_migrations

# Миграции при старте — дашборд и бот используют одну БД,
# но запускаются как отдельные процессы. Каждый должен применять миграции.
run_migrations()

app = FastAPI(
    title="Job Hunt Dashboard",
    description="Дашборд для отслеживания вакансий и событий",
    version="1.0.0",
    # Отключаем публичную документацию — дашборд личный
    docs_url=None,
    redoc_url=None,
)

# CORS для локальной разработки (Vite dev server на :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API роутеры
app.include_router(stats.router)
app.include_router(vacancies.router)
app.include_router(events.router)

# Статические файлы React — монтируем если билд существует
_STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if _STATIC_DIR.exists():
    # SPA: все неизвестные пути отдают index.html (React Router обрабатывает на клиенте)
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="frontend")
