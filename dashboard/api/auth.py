"""
HTTP Basic Auth для дашборда (SRP).
Credentials берутся из .env (DASHBOARD_USER / DASHBOARD_PASSWORD).
"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.config import config

security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Dependency: проверяет логин/пароль. Использовать в каждом роутере."""
    ok_user = secrets.compare_digest(credentials.username, config.dashboard_user)
    ok_pass = secrets.compare_digest(credentials.password, config.dashboard_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
