from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Any

import config
from bot import telegram

LOG_FILE = config.LOGS_DIR / 'general.log'
ERROR_STATE_FILE = config.DATA_DIR / 'error_state.json'
ERROR_LEVEL_MARKERS = (' - ERROR - ', ' - CRITICAL - ')
logger = logging.getLogger('bothr')


def setup_logger() -> None:
    if logger.handlers:
        return

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False


def log_event(message: str, level: int = logging.INFO) -> None:
    logger.log(level, message)


async def notify_telegram(message: str) -> None:
    try:
        await telegram.send_message(config.CHAT_ID, message)
    except Exception:
        logger.exception('No se pudo enviar el mensaje de Telegram: %s', message[:120])


def _read_recent_log_lines(limit: int) -> list[str]:
    if limit <= 0 or not LOG_FILE.exists():
        return []

    with LOG_FILE.open('rb') as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        if file_size <= 0:
            return []

        block_size = 4096
        position = file_size
        buffer = b''
        line_count = 0

        while position > 0 and line_count < limit:
            chunk_size = min(block_size, position)
            position -= chunk_size
            handle.seek(position)
            chunk = handle.read(chunk_size)
            buffer = chunk + buffer
            line_count += chunk.count(b'\n')

    return [line.decode('utf-8', errors='replace') for line in buffer.splitlines()[-limit:]]


def tail_log_lines(limit: int = 100) -> list[str]:
    return _read_recent_log_lines(limit)


def get_last_error_line(limit: int = 300) -> str | None:
    if not LOG_FILE.exists():
        return None
    recent_lines = _read_recent_log_lines(limit)
    for index in range(len(recent_lines) - 1, -1, -1):
        line = recent_lines[index]
        if any(marker in line for marker in ERROR_LEVEL_MARKERS):
            return line
    return None


def _load_error_state() -> dict[str, Any]:
    payload = config.read_json_file(ERROR_STATE_FILE, default={})
    return payload if isinstance(payload, dict) else {}


def _save_error_state(payload: dict[str, Any]) -> None:
    config.write_json_file(ERROR_STATE_FILE, payload)


def get_visible_last_error() -> str | None:
    last_error = get_last_error_line()
    if not last_error:
        return None
    seen_last_error = _load_error_state().get('seen_last_error')
    return None if seen_last_error == last_error else last_error


def mark_last_error_as_seen() -> None:
    last_error = get_last_error_line()
    if last_error is None:
        _save_error_state({})
        return
    _save_error_state({'seen_last_error': last_error})
