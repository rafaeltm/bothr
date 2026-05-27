from __future__ import annotations

import json
import os
import threading
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env"
TZ = ZoneInfo("Europe/Madrid")
MASK_VALUE = "***...***"

MANAGED_ENV_KEYS = [
    "USERNAME",
    "PASSWORD",
    "CHAT_ID",
    "BOT_TOKEN",
    "ENABLE",
    "LATITUDE",
    "LONGITUDE",
    "LOGIN_URL",
    "FICHAJE_FILE",
    "FESTIVOS_FILE",
    "JORNADA_REDUCIDA_FILE",
    "PREFERRED_CLOCK_IN",
    "DASHBOARD_PASSWORD",
    "DASHBOARD_PORT",
    "TEAMLEADER_ENABLED",
    "TEAMLEADER_CLIENT_ID",
    "TEAMLEADER_CLIENT_SECRET",
    "TEAMLEADER_REDIRECT_URI",
    "TEAMLEADER_AUTH_BASE_URL",
    "TEAMLEADER_API_BASE_URL",
    "TEAMLEADER_ACCESS_TOKEN",
    "TEAMLEADER_REFRESH_TOKEN",
    "TEAMLEADER_TOKEN_EXPIRES_AT",
    "TEAMLEADER_ACCOUNT_ID",
    "TEAMLEADER_TASK_ID",
    "TEAMLEADER_WORKDAY_START",
    "TEAMLEADER_WORKDAY_END",
    "JIRA_ENABLED",
    "JIRA_TEMPO_BASE_URL",
    "JIRA_TEMPO_API_TOKEN",
    "JIRA_WORK_ISSUE",
    "JIRA_VACATION_ISSUE",
    "JIRA_WORKDAY_START",
    "JIRA_WORKDAY_END",
    "VACACIONES_FILE",
]
SENSITIVE_ENV_KEYS = {
    "PASSWORD",
    "BOT_TOKEN",
    "CHAT_ID",
    "DASHBOARD_PASSWORD",
    "TEAMLEADER_CLIENT_SECRET",
    "TEAMLEADER_ACCESS_TOKEN",
    "TEAMLEADER_REFRESH_TOKEN",
    "JIRA_TEMPO_API_TOKEN",
}

USERNAME: str | None = None
PASSWORD: str | None = None
CHAT_ID: str | None = None
BOT_TOKEN: str | None = None
ENABLE: bool = False
LATITUDE: float | None = None
LONGITUDE: float | None = None
LOGIN_URL: str | None = None
FICHAJE_FILE: Path = DATA_DIR / "fichaje.json"
FESTIVOS_FILE: Path = DATA_DIR / "festivos.json"
JORNADA_REDUCIDA_FILE: Path = DATA_DIR / "jornada_reducida.json"
VACACIONES_FILE: Path = DATA_DIR / "vacaciones.json"
PREFERRED_CLOCK_IN: time = time(hour=8, minute=0)
DASHBOARD_PASSWORD: str = "admin"
DASHBOARD_PORT: int = 5000
TEAMLEADER_ENABLED: bool = False
TEAMLEADER_CLIENT_ID: str | None = None
TEAMLEADER_CLIENT_SECRET: str | None = None
TEAMLEADER_REDIRECT_URI: str | None = None
TEAMLEADER_AUTH_BASE_URL: str = "https://app.teamleader.eu"
TEAMLEADER_API_BASE_URL: str = "https://api.focus.teamleader.eu"
TEAMLEADER_ACCESS_TOKEN: str | None = None
TEAMLEADER_REFRESH_TOKEN: str | None = None
TEAMLEADER_TOKEN_EXPIRES_AT: str | None = None
TEAMLEADER_ACCOUNT_ID: str | None = None
TEAMLEADER_TASK_ID: str | None = None
TEAMLEADER_WORKDAY_START: str = "08:00"
TEAMLEADER_WORKDAY_END: str = "17:00"
JIRA_ENABLED: bool = False
JIRA_TEMPO_BASE_URL: str = "https://api.tempo.io"
JIRA_TEMPO_API_TOKEN: str | None = None
JIRA_WORK_ISSUE: str | None = None
JIRA_VACATION_ISSUE: str | None = None
JIRA_WORKDAY_START: str = "08:00"
JIRA_WORKDAY_END: str = "17:00"
_file_locks_mutex = threading.Lock()
_file_locks: dict[Path, threading.RLock] = {}
_calendar_cache_lock = threading.Lock()
_festivos_cache: set[str] | None = None
_jornada_reducida_cache: set[str] | None = None
_vacaciones_cache: set[str] | None = None


def _resolve_path(value: str | None, default: str) -> Path:
    path = Path(value) if value else Path(default)
    return path if path.is_absolute() else BASE_DIR / path


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str) -> float | None:
    value = os.getenv(name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_time(name: str, default: time) -> time:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = time.fromisoformat(value.strip())
        return parsed.replace(second=0, microsecond=0)
    except ValueError:
        return default


def refresh(force_file_override: bool = False) -> None:
    """Reload environment-backed module settings.

    By default, keep compatibility with previous behavior where process env values
    are not overridden by .env values. When `force_file_override=True`, values from
    ENV_FILE override the process env (used by dashboard runtime updates). The
    first call intentionally uses dotenv discovery behavior (including parent dirs)
    to remain compatible with previous deployments.
    """
    # 1) Preserve legacy behavior: discover .env without overriding existing process env.
    load_dotenv(override=False)
    # 2) Optionally override from our managed ENV_FILE so dashboard changes apply at runtime.
    load_dotenv(ENV_FILE, override=force_file_override)

    globals().update(
        {
            "USERNAME": os.getenv("USERNAME") or None,
            "PASSWORD": os.getenv("PASSWORD") or None,
            "CHAT_ID": os.getenv("CHAT_ID") or None,
            "BOT_TOKEN": os.getenv("BOT_TOKEN") or None,
            "ENABLE": _get_bool("ENABLE", default=False),
            "LATITUDE": _get_float("LATITUDE"),
            "LONGITUDE": _get_float("LONGITUDE"),
            "LOGIN_URL": os.getenv("LOGIN_URL") or None,
            "FICHAJE_FILE": _resolve_path(os.getenv("FICHAJE_FILE"), "data/fichaje.json"),
            "FESTIVOS_FILE": _resolve_path(os.getenv("FESTIVOS_FILE"), "data/festivos.json"),
            "JORNADA_REDUCIDA_FILE": _resolve_path(
                os.getenv("JORNADA_REDUCIDA_FILE"),
                "data/jornada_reducida.json",
            ),
            "VACACIONES_FILE": _resolve_path(os.getenv("VACACIONES_FILE"), "data/vacaciones.json"),
            "PREFERRED_CLOCK_IN": _get_time("PREFERRED_CLOCK_IN", time(hour=8, minute=0)),
            "DASHBOARD_PASSWORD": os.getenv("DASHBOARD_PASSWORD") or "admin",
            "DASHBOARD_PORT": _get_int("DASHBOARD_PORT", 5000),
            "TEAMLEADER_ENABLED": _get_bool("TEAMLEADER_ENABLED", default=False),
            "TEAMLEADER_CLIENT_ID": os.getenv("TEAMLEADER_CLIENT_ID") or None,
            "TEAMLEADER_CLIENT_SECRET": os.getenv("TEAMLEADER_CLIENT_SECRET") or None,
            "TEAMLEADER_REDIRECT_URI": os.getenv("TEAMLEADER_REDIRECT_URI") or None,
            "TEAMLEADER_AUTH_BASE_URL": os.getenv("TEAMLEADER_AUTH_BASE_URL")
            or "https://app.teamleader.eu",
            "TEAMLEADER_API_BASE_URL": os.getenv("TEAMLEADER_API_BASE_URL")
            or "https://api.focus.teamleader.eu",
            "TEAMLEADER_ACCESS_TOKEN": os.getenv("TEAMLEADER_ACCESS_TOKEN") or None,
            "TEAMLEADER_REFRESH_TOKEN": os.getenv("TEAMLEADER_REFRESH_TOKEN") or None,
            "TEAMLEADER_TOKEN_EXPIRES_AT": os.getenv("TEAMLEADER_TOKEN_EXPIRES_AT") or None,
            "TEAMLEADER_ACCOUNT_ID": os.getenv("TEAMLEADER_ACCOUNT_ID") or None,
            "TEAMLEADER_TASK_ID": os.getenv("TEAMLEADER_TASK_ID") or None,
            "TEAMLEADER_WORKDAY_START": os.getenv("TEAMLEADER_WORKDAY_START") or "08:00",
            "TEAMLEADER_WORKDAY_END": os.getenv("TEAMLEADER_WORKDAY_END") or "17:00",
            "JIRA_ENABLED": _get_bool("JIRA_ENABLED", default=False),
            "JIRA_TEMPO_BASE_URL": os.getenv("JIRA_TEMPO_BASE_URL") or "https://api.tempo.io",
            "JIRA_TEMPO_API_TOKEN": os.getenv("JIRA_TEMPO_API_TOKEN") or None,
            "JIRA_WORK_ISSUE": os.getenv("JIRA_WORK_ISSUE") or None,
            "JIRA_VACATION_ISSUE": os.getenv("JIRA_VACATION_ISSUE") or None,
            "JIRA_WORKDAY_START": os.getenv("JIRA_WORKDAY_START") or "08:00",
            "JIRA_WORKDAY_END": os.getenv("JIRA_WORKDAY_END") or "17:00",
        }
    )
    invalidate_calendar_cache()


def _load_json_dates(path: Path, key: str) -> set[str]:
    """Load date strings from a JSON file and return them as a set."""
    try:
        with path.open('r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()

    values = data.get(key, [])
    if not isinstance(values, list):
        return set()
    return {str(item) for item in values}


def invalidate_calendar_cache() -> None:
    global _festivos_cache, _jornada_reducida_cache, _vacaciones_cache
    with _calendar_cache_lock:
        _festivos_cache = None
        _jornada_reducida_cache = None
        _vacaciones_cache = None


refresh()


def load_festivos() -> set[str]:
    global _festivos_cache
    with _calendar_cache_lock:
        if _festivos_cache is None:
            _festivos_cache = _load_json_dates(FESTIVOS_FILE, 'festivos')
        return set(_festivos_cache)



def load_jornada_reducida() -> set[str]:
    global _jornada_reducida_cache
    with _calendar_cache_lock:
        if _jornada_reducida_cache is None:
            _jornada_reducida_cache = _load_json_dates(JORNADA_REDUCIDA_FILE, 'dias')
        return set(_jornada_reducida_cache)



def load_vacaciones() -> set[str]:
    global _vacaciones_cache
    with _calendar_cache_lock:
        if _vacaciones_cache is None:
            _vacaciones_cache = _load_json_dates(VACACIONES_FILE, 'dias')
        return set(_vacaciones_cache)



def get_current_settings(mask_sensitive: bool = False, mask: str = '***') -> dict[str, Any]:
    values: dict[str, Any] = {
        'USERNAME': USERNAME or '',
        'PASSWORD': PASSWORD or '',
        'CHAT_ID': CHAT_ID or '',
        'BOT_TOKEN': BOT_TOKEN or '',
        'ENABLE': ENABLE,
        'LATITUDE': LATITUDE if LATITUDE is not None else '',
        'LONGITUDE': LONGITUDE if LONGITUDE is not None else '',
        'LOGIN_URL': LOGIN_URL or '',
        'FICHAJE_FILE': str(FICHAJE_FILE),
        'FESTIVOS_FILE': str(FESTIVOS_FILE),
        'JORNADA_REDUCIDA_FILE': str(JORNADA_REDUCIDA_FILE),
        'VACACIONES_FILE': str(VACACIONES_FILE),
        'PREFERRED_CLOCK_IN': PREFERRED_CLOCK_IN.strftime('%H:%M'),
        'DASHBOARD_PASSWORD': DASHBOARD_PASSWORD or '',
        'DASHBOARD_PORT': DASHBOARD_PORT,
        'TEAMLEADER_ENABLED': TEAMLEADER_ENABLED,
        'TEAMLEADER_CLIENT_ID': TEAMLEADER_CLIENT_ID or '',
        'TEAMLEADER_CLIENT_SECRET': TEAMLEADER_CLIENT_SECRET or '',
        'TEAMLEADER_REDIRECT_URI': TEAMLEADER_REDIRECT_URI or '',
        'TEAMLEADER_AUTH_BASE_URL': TEAMLEADER_AUTH_BASE_URL or '',
        'TEAMLEADER_API_BASE_URL': TEAMLEADER_API_BASE_URL or '',
        'TEAMLEADER_ACCESS_TOKEN': TEAMLEADER_ACCESS_TOKEN or '',
        'TEAMLEADER_REFRESH_TOKEN': TEAMLEADER_REFRESH_TOKEN or '',
        'TEAMLEADER_TOKEN_EXPIRES_AT': TEAMLEADER_TOKEN_EXPIRES_AT or '',
        'TEAMLEADER_ACCOUNT_ID': TEAMLEADER_ACCOUNT_ID or '',
        'TEAMLEADER_TASK_ID': TEAMLEADER_TASK_ID or '',
        'TEAMLEADER_WORKDAY_START': TEAMLEADER_WORKDAY_START or '',
        'TEAMLEADER_WORKDAY_END': TEAMLEADER_WORKDAY_END or '',
        'JIRA_ENABLED': JIRA_ENABLED,
        'JIRA_TEMPO_BASE_URL': JIRA_TEMPO_BASE_URL or '',
        'JIRA_TEMPO_API_TOKEN': JIRA_TEMPO_API_TOKEN or '',
        'JIRA_WORK_ISSUE': JIRA_WORK_ISSUE or '',
        'JIRA_VACATION_ISSUE': JIRA_VACATION_ISSUE or '',
        'JIRA_WORKDAY_START': JIRA_WORKDAY_START or '',
        'JIRA_WORKDAY_END': JIRA_WORKDAY_END or '',
    }
    if mask_sensitive:
        for key in SENSITIVE_ENV_KEYS:
            if values.get(key):
                values[key] = mask
    return values



def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_file_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _file_locks_mutex:
        lock = _file_locks.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _file_locks[resolved] = lock
    return lock


def read_json_file(path: Path, default: Any) -> Any:
    lock = get_file_lock(path)
    with lock:
        try:
            with path.open('r', encoding='utf-8') as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default


def write_json_file(path: Path, payload: Any) -> None:
    lock = get_file_lock(path)
    with lock:
        ensure_parent(path)
        with path.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
