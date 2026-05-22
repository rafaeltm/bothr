from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import deque
from datetime import datetime, time, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from playwright.async_api import async_playwright

import config
from bot import fichaje, telegram

LOG_FILE = config.LOGS_DIR / 'general.log'
logger = logging.getLogger('bothr')


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
    except Exception:
        logger.exception('No se pudo enviar el mensaje de Telegram.')



def read_fichaje_log() -> list[dict[str, str]]:
    """Return persisted fichaje entries or an empty list on read errors."""
    try:
        with config.FICHAJE_FILE.open('r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []



def es_fichaje_realizado_hoy(tipo: str) -> bool:
    """Check whether the given fichaje type has already been recorded today."""
    today = datetime.now(config.TZ).date()
    for registro in read_fichaje_log():
        timestamp = registro.get(tipo)
        if not timestamp:
            continue
        try:
            fecha = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').date()
        except ValueError:
            continue
        if fecha == today:
            return True
    return False


def get_fichaje_hoy(tipo: str) -> str | None:
    """Return latest today's timestamp for `entrada` or `salida`, when available."""
    today = datetime.now(config.TZ).date()
    today_values: list[str] = []
    for registro in read_fichaje_log():
        timestamp = registro.get(tipo)
        if not timestamp:
            continue
        try:
            fecha = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').date()
        except ValueError:
            continue
        if fecha == today:
            today_values.append(timestamp)
    return max(today_values) if today_values else None



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



def get_fichaje_hours(reference: datetime | None = None) -> dict[str, time] | None:
    """Calculate stable daily clock-in and clock-out times for working days."""
    now = reference or datetime.now(config.TZ)
    if now.weekday() >= 5 or now.strftime('%Y-%m-%d') in config.load_festivos():
        return None

    seed = int(now.strftime('%Y%m%d'))
    margin_minutes = random.Random(seed).randint(-15, 15)
    base_entry = datetime.combine(now.date(), time(hour=8, minute=0), tzinfo=config.TZ)
    clock_in_dt = base_entry + timedelta(minutes=margin_minutes)

    today_str = now.strftime('%Y-%m-%d')
    if today_str in config.load_jornada_reducida():
        work_hours = 7
    else:
        work_hours = 7 if (6 <= now.month <= 9 or now.weekday() == 4) else 9

    clock_out_dt = clock_in_dt + timedelta(hours=work_hours)
    return {'clock_in': clock_in_dt.time().replace(microsecond=0), 'clock_out': clock_out_dt.time().replace(microsecond=0)}


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
    for _ in range(366):
        hours = get_fichaje_hours(cursor)
        if hours is not None:
            target = datetime.combine(cursor.date(), hours['clock_in'], tzinfo=config.TZ)
            if target > reference:
                return target
        cursor = datetime.combine((cursor + timedelta(days=1)).date(), time.min, tzinfo=config.TZ)
    raise RuntimeError('No se encontró un día laborable en los próximos 366 días.')



def get_status_payload() -> dict[str, object]:
    now = datetime.now(config.TZ)
    hours = get_fichaje_hours(now)
    today_clocked_in_at = get_fichaje_hoy('entrada')
    today_clocked_out_at = get_fichaje_hoy('salida')
    today_clocked_in = today_clocked_in_at is not None
    today_clocked_out = today_clocked_out_at is not None

    if es_festivo(now) or hours is None:
        try:
            next_working_entry = _next_working_clock_in(now)
        except RuntimeError:
            return {
                'next_action': 'ninguna',
                'next_action_at': None,
                'time_remaining': 'Sin día laborable configurado',
                'today_clocked_in': today_clocked_in,
                'today_clocked_out': today_clocked_out,
                'today_clocked_in_at': today_clocked_in_at,
                'today_clocked_out_at': today_clocked_out_at,
            }
        return {
            'next_action': 'entrada',
            'next_action_at': next_working_entry.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': _format_seconds((next_working_entry - now).total_seconds()),
            'today_clocked_in': today_clocked_in,
            'today_clocked_out': today_clocked_out,
            'today_clocked_in_at': today_clocked_in_at,
            'today_clocked_out_at': today_clocked_out_at,
        }

    if not today_clocked_in:
        target = datetime.combine(now.date(), hours['clock_in'], tzinfo=config.TZ)
        return {
            'next_action': 'entrada',
            'next_action_at': target.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': _format_seconds(_seconds_until(hours['clock_in'])),
            'today_clocked_in': today_clocked_in,
            'today_clocked_out': today_clocked_out,
            'today_clocked_in_at': today_clocked_in_at,
            'today_clocked_out_at': today_clocked_out_at,
        }

    if not today_clocked_out:
        target = datetime.combine(now.date(), hours['clock_out'], tzinfo=config.TZ)
        return {
            'next_action': 'salida',
            'next_action_at': target.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': _format_seconds(_seconds_until(hours['clock_out'])),
            'today_clocked_in': today_clocked_in,
            'today_clocked_out': today_clocked_out,
            'today_clocked_in_at': today_clocked_in_at,
            'today_clocked_out_at': today_clocked_out_at,
        }

    try:
        next_working_entry = _next_working_clock_in(now)
    except RuntimeError:
        return {
            'next_action': 'ninguna',
            'next_action_at': None,
            'time_remaining': 'Sin día laborable configurado',
            'today_clocked_in': today_clocked_in,
            'today_clocked_out': today_clocked_out,
            'today_clocked_in_at': today_clocked_in_at,
            'today_clocked_out_at': today_clocked_out_at,
        }
    return {
        'next_action': 'entrada',
        'next_action_at': next_working_entry.strftime('%Y-%m-%d %H:%M:%S'),
        'time_remaining': _format_seconds((next_working_entry - now).total_seconds()),
        'today_clocked_in': today_clocked_in,
        'today_clocked_out': today_clocked_out,
        'today_clocked_in_at': today_clocked_in_at,
        'today_clocked_out_at': today_clocked_out_at,
    }



def tail_log_lines(limit: int = 100) -> list[str]:
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open('r', encoding='utf-8') as handle:
        return [line.rstrip("\n") for line in deque(handle, maxlen=limit)]


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
