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
]
SENSITIVE_ENV_KEYS = {"PASSWORD", "BOT_TOKEN", "CHAT_ID", "DASHBOARD_PASSWORD"}

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
PREFERRED_CLOCK_IN: time = time(hour=8, minute=0)
DASHBOARD_PASSWORD: str = "admin"
DASHBOARD_PORT: int = 5000
_file_locks_mutex = threading.Lock()
_file_locks: dict[Path, threading.RLock] = {}
_festivos_cache: set[str] | None = None
_jornada_reducida_cache: set[str] | None = None


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
            "PREFERRED_CLOCK_IN": _get_time("PREFERRED_CLOCK_IN", time(hour=8, minute=0)),
            "DASHBOARD_PASSWORD": os.getenv("DASHBOARD_PASSWORD") or "admin",
            "DASHBOARD_PORT": _get_int("DASHBOARD_PORT", 5000),
        }
    )
    invalidate_calendar_cache()


refresh()


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
    global _festivos_cache, _jornada_reducida_cache
    _festivos_cache = None
    _jornada_reducida_cache = None


def load_festivos() -> set[str]:
    global _festivos_cache
    if _festivos_cache is None:
        _festivos_cache = _load_json_dates(FESTIVOS_FILE, 'festivos')
    return set(_festivos_cache)



def load_jornada_reducida() -> set[str]:
    global _jornada_reducida_cache
    if _jornada_reducida_cache is None:
        _jornada_reducida_cache = _load_json_dates(JORNADA_REDUCIDA_FILE, 'dias')
    return set(_jornada_reducida_cache)



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
        'PREFERRED_CLOCK_IN': PREFERRED_CLOCK_IN.strftime('%H:%M'),
        'DASHBOARD_PASSWORD': DASHBOARD_PASSWORD or '',
        'DASHBOARD_PORT': DASHBOARD_PORT,
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
