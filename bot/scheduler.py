from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import datetime, time, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from playwright.async_api import async_playwright

import config
from bot import fichaje, telegram

LOG_FILE = config.LOGS_DIR / 'general.log'
MAX_WORKDAY_LOOKAHEAD_DAYS = 366
REDUCED_WORK_HOURS = 7
STANDARD_WORK_HOURS = 9
logger = logging.getLogger('bothr')
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
# Supports timestamps like:
# - YYYY-MM-DD HH:MM:SS
# - YYYY-MM-DDTHH:MM:SS
# - optional fractional seconds (.sss or ,sss)
# - optional timezone suffix (Z, +HHMM, +HH:MM)
TIMESTAMP_PATTERN = re.compile(r'(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)')
OFFSET_WITH_COLON_PATTERN = re.compile(r'(?P<hours>[+-]\d{2}):(?P<minutes>\d{2})$')
ACTION_PATTERN = re.compile(r'\b(entrada|salida)\b')
ERROR_LEVEL_MARKERS = (' - ERROR - ', ' - CRITICAL - ')


def _setup_logger() -> None:
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


_setup_logger()


async def log_event(message: str, level: int = logging.INFO) -> None:
    logger.log(level, message)
    try:
        await telegram.send_message(config.CHAT_ID, message)
    except Exception as exc:
        logger.exception('No se pudo enviar el mensaje de Telegram: %s', exc)



def _parse_timestamp(timestamp: str) -> datetime | None:
    for fmt in (DATETIME_FORMAT, '%Y-%m-%dT%H:%M:%S'):
        try:
            parsed = datetime.strptime(timestamp, fmt)
            return parsed.replace(tzinfo=config.TZ)
        except ValueError:
            continue

    normalized = timestamp.replace(',', '.')
    if normalized.endswith('Z'):
        normalized = f'{normalized[:-1]}+00:00'
    # Accept timezone offsets with colon by normalizing +HH:MM -> +HHMM for strict parsers.
    normalized = OFFSET_WITH_COLON_PATTERN.sub(
        lambda match: f"{match.group('hours')}{match.group('minutes')}",
        normalized,
    )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=config.TZ)
    return parsed.astimezone(config.TZ)


def _to_fichaje_record(line: str) -> dict[str, str] | None:
    lowered = line.lower()
    actions = ACTION_PATTERN.findall(lowered)
    unique_actions = set(actions)
    if len(unique_actions) != 1:
        return None
    tipo = next(iter(unique_actions))

    match = TIMESTAMP_PATTERN.search(line)
    if not match:
        return None
    parsed = _parse_timestamp(match.group('timestamp'))
    if parsed is None:
        return None
    return {tipo: parsed.strftime(DATETIME_FORMAT)}


def read_fichaje_log() -> list[dict[str, str]]:
    """Return persisted fichaje entries from JSON or text logs."""
    try:
        with config.FICHAJE_FILE.open('r', encoding='utf-8') as handle:
            raw_data = handle.read()
    except (FileNotFoundError, OSError):
        return []

    text = raw_data.strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        normalized: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            normalized_item: dict[str, str] = {}
            for tipo in ('entrada', 'salida'):
                timestamp = item.get(tipo)
                if not isinstance(timestamp, str):
                    continue
                parsed = _parse_timestamp(timestamp)
                if parsed is None:
                    continue
                normalized_item[tipo] = parsed.strftime(DATETIME_FORMAT)
            if normalized_item:
                normalized.append(normalized_item)
        return normalized

    records: list[dict[str, str]] = []
    for line in text.splitlines():
        record = _to_fichaje_record(line)
        if record is not None:
            records.append(record)
    return records



def es_fichaje_realizado_hoy(tipo: str) -> bool:
    """Check whether the given fichaje type has already been recorded today."""
    today = datetime.now(config.TZ).date()
    for registro in read_fichaje_log():
        timestamp = registro.get(tipo)
        if not timestamp:
            continue
        parsed = _parse_timestamp(timestamp)
        if parsed is None:
            continue
        fecha = parsed.date()
        if fecha == today:
            return True
    return False


def get_fichaje_hoy(tipo: str) -> str | None:
    """Return latest today's timestamp for `entrada` or `salida`, when available."""
    today = datetime.now(config.TZ).date()
    today_timestamps: list[datetime] = []
    for registro in read_fichaje_log():
        timestamp = registro.get(tipo)
        if not timestamp:
            continue
        parsed = _parse_timestamp(timestamp)
        if parsed is None:
            continue
        fecha = parsed.date()
        if fecha == today:
            # `_parse_timestamp` normalizes all parsed values to `config.TZ`.
            today_timestamps.append(parsed)
    return max(today_timestamps).strftime(DATETIME_FORMAT) if today_timestamps else None



def write_fichaje_log(tipo: str, timestamp: str) -> None:
    registros = read_fichaje_log()
    registros.append({tipo: timestamp})
    config.ensure_parent(config.FICHAJE_FILE)
    with config.FICHAJE_FILE.open('w', encoding='utf-8') as handle:
        json.dump(registros, handle, indent=2, ensure_ascii=False)



def es_festivo(reference: datetime | None = None) -> bool:
    """Return True when the supplied date is a weekend or configured holiday."""
    now = reference or datetime.now(config.TZ)
    today_str = now.strftime('%Y-%m-%d')
    return now.weekday() >= 5 or today_str in config.load_festivos()


def _get_work_hours(reference: datetime) -> int:
    today_str = reference.strftime('%Y-%m-%d')
    if reference.weekday() == 4 or today_str in config.load_jornada_reducida() or 6 <= reference.month <= 9:
        return REDUCED_WORK_HOURS
    return STANDARD_WORK_HOURS


def _get_daily_clock_in_time(reference: datetime) -> time:
    preferred_clock_in = datetime.combine(reference.date(), config.PREFERRED_CLOCK_IN, tzinfo=config.TZ)
    seeded_random = random.Random(reference.date().isoformat())
    random_margin = timedelta(minutes=seeded_random.randint(-15, 15))
    return (preferred_clock_in + random_margin).time().replace(microsecond=0)


def get_fichaje_hours(reference: datetime | None = None) -> dict[str, time] | None:
    """Calculate stable daily clock-in and clock-out times for working days."""
    now = reference or datetime.now(config.TZ)
    if now.weekday() >= 5 or now.strftime('%Y-%m-%d') in config.load_festivos():
        return None

    clock_in_time = _get_daily_clock_in_time(now)
    preferred_clock_in_dt = datetime.combine(now.date(), config.PREFERRED_CLOCK_IN, tzinfo=config.TZ)
    work_hours = _get_work_hours(now)
    clock_out_dt = preferred_clock_in_dt + timedelta(hours=work_hours)
    return {'clock_in': clock_in_time, 'clock_out': clock_out_dt.time().replace(microsecond=0)}


async def esperar_hora(target_time: time) -> None:
    now = datetime.now(config.TZ)
    target = datetime.combine(now.date(), target_time, tzinfo=config.TZ)
    if target <= now:
        target += timedelta(days=1)
    seconds = max((target - now).total_seconds(), 0)
    logger.info('Esperando hasta las %s (%.0f segundos).', target.strftime('%Y-%m-%d %H:%M:%S'), seconds)
    await asyncio.sleep(seconds)



def _format_seconds(total_seconds: float) -> str:
    remaining = max(int(total_seconds), 0)
    hours, remainder = divmod(remaining, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'



def _seconds_until(target_time: time) -> float:
    now = datetime.now(config.TZ)
    target = datetime.combine(now.date(), target_time, tzinfo=config.TZ)
    return max((target - now).total_seconds(), 0)


def _next_working_clock_in(reference: datetime) -> datetime:
    cursor = reference
    for _ in range(MAX_WORKDAY_LOOKAHEAD_DAYS):
        hours = get_fichaje_hours(cursor)
        if hours is not None:
            target = datetime.combine(cursor.date(), hours['clock_in'], tzinfo=config.TZ)
            if target > reference:
                return target
        cursor = datetime.combine((cursor + timedelta(days=1)).date(), time.min, tzinfo=config.TZ)
    raise RuntimeError(f'No se encontró un día laborable en los próximos {MAX_WORKDAY_LOOKAHEAD_DAYS} días.')



def _read_recent_log_lines(limit: int) -> list[str]:
    """Read up to `limit` lines from the end of the scheduler log file.

    Log bytes are decoded as UTF-8 with replacement to tolerate malformed/non-UTF-8 entries.
    """
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

    lines = [
        line.decode('utf-8', errors='replace')
        for line in buffer.splitlines()[-limit:]
    ]
    return lines


def get_last_error_line(limit: int = 300) -> str | None:
    """Return the most recent ERROR/CRITICAL log line from the last `limit` entries."""
    if not LOG_FILE.exists():
        return None
    recent_lines = _read_recent_log_lines(limit)
    for index in range(len(recent_lines) - 1, -1, -1):
        line = recent_lines[index]
        if any(marker in line for marker in ERROR_LEVEL_MARKERS):
            return line
    return None


def get_status_payload() -> dict[str, object]:
    now = datetime.now(config.TZ)
    hours = get_fichaje_hours(now)
    today_clocked_in_at = get_fichaje_hoy('entrada')
    today_clocked_out_at = get_fichaje_hoy('salida')
    today_clocked_in = today_clocked_in_at is not None
    today_clocked_out = today_clocked_out_at is not None
    base_payload = {
        'today_clocked_in': today_clocked_in,
        'today_clocked_out': today_clocked_out,
        'today_clocked_in_at': today_clocked_in_at,
        'today_clocked_out_at': today_clocked_out_at,
        'preferred_clock_in': config.PREFERRED_CLOCK_IN.strftime('%H:%M'),
        'planned_clock_in': hours['clock_in'].strftime('%H:%M') if hours else None,
        'planned_clock_out': hours['clock_out'].strftime('%H:%M') if hours else None,
        'last_error': get_last_error_line(),
    }

    if es_festivo(now) or hours is None:
        try:
            next_working_entry = _next_working_clock_in(now)
        except RuntimeError:
            return {
                **base_payload,
                'next_action': 'ninguna',
                'next_action_at': None,
                'time_remaining': 'Sin día laborable configurado',
            }
        return {
            **base_payload,
            'next_action': 'entrada',
            'next_action_at': next_working_entry.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': _format_seconds((next_working_entry - now).total_seconds()),
        }

    if not today_clocked_in:
        target = datetime.combine(now.date(), hours['clock_in'], tzinfo=config.TZ)
        return {
            **base_payload,
            'next_action': 'entrada',
            'next_action_at': target.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': _format_seconds(_seconds_until(hours['clock_in'])),
        }

    if not today_clocked_out:
        target = datetime.combine(now.date(), hours['clock_out'], tzinfo=config.TZ)
        return {
            **base_payload,
            'next_action': 'salida',
            'next_action_at': target.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': _format_seconds(_seconds_until(hours['clock_out'])),
        }

    try:
        next_working_entry = _next_working_clock_in(now)
    except RuntimeError:
        return {
            **base_payload,
            'next_action': 'ninguna',
            'next_action_at': None,
            'time_remaining': 'Sin día laborable configurado',
        }
    return {
        **base_payload,
        'next_action': 'entrada',
        'next_action_at': next_working_entry.strftime('%Y-%m-%d %H:%M:%S'),
        'time_remaining': _format_seconds((next_working_entry - now).total_seconds()),
    }



def tail_log_lines(limit: int = 100) -> list[str]:
    return _read_recent_log_lines(limit)


async def _perform_fichaje(tipo: str) -> bool:
    async with async_playwright() as playwright:
        page, browser = await fichaje.login(playwright)
        if not page or not browser:
            return False
        try:
            success = await fichaje.fichar(page, tipo)
            if success:
                write_fichaje_log(tipo, datetime.now(config.TZ).strftime('%Y-%m-%d %H:%M:%S'))
                await log_event(f'Fichaje de {tipo} completado.')
            return success
        finally:
            await browser.close()


async def run() -> None:
    await log_event('Scheduler iniciado.')
    while True:
        try:
            now = datetime.now(config.TZ)
            hours = get_fichaje_hours(now)

            if es_festivo(now) or hours is None:
                await log_event('Hoy no es laborable. Esperando al siguiente día.')
                await esperar_hora(time.min)
                continue

            if not es_fichaje_realizado_hoy('entrada'):
                await log_event(f"Esperando fichaje de entrada a las {hours['clock_in'].strftime('%H:%M:%S')}.")
                await esperar_hora(hours['clock_in'])
                if not es_fichaje_realizado_hoy('entrada') and not es_festivo():
                    if not await _perform_fichaje('entrada'):
                        await asyncio.sleep(60)
                continue

            if not es_fichaje_realizado_hoy('salida'):
                await log_event(f"Esperando fichaje de salida a las {hours['clock_out'].strftime('%H:%M:%S')}.")
                await esperar_hora(hours['clock_out'])
                if not es_fichaje_realizado_hoy('salida') and not es_festivo():
                    if not await _perform_fichaje('salida'):
                        await asyncio.sleep(60)
                continue

            await log_event('Entrada y salida ya registradas hoy. Esperando al siguiente día.')
            await esperar_hora(time.min)
        except Exception as exc:
            logger.exception('Error no controlado en scheduler: %s', exc)
            await telegram.send_message(config.CHAT_ID, f'Error no controlado en scheduler: {exc}')
            await asyncio.sleep(60)
