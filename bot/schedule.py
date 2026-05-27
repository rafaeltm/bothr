from __future__ import annotations

import asyncio
import random
from datetime import datetime, time, timedelta

import config

MAX_WORKDAY_LOOKAHEAD_DAYS = 366
REDUCED_WORK_HOURS = 7
STANDARD_WORK_HOURS = 9


def es_festivo(reference: datetime | None = None) -> bool:
    now = reference or datetime.now(config.TZ)
    today_str = now.strftime('%Y-%m-%d')
    return now.weekday() >= 5 or today_str in config.load_festivos()


def is_working_day(reference: datetime) -> bool:
    return not es_festivo(reference)


def _get_work_hours(reference: datetime) -> int:
    today_str = reference.strftime('%Y-%m-%d')
    if reference.weekday() == 4 or today_str in config.load_jornada_reducida() or 6 <= reference.month <= 9:
        return REDUCED_WORK_HOURS
    return STANDARD_WORK_HOURS


def get_work_hours(reference: datetime) -> int:
    return _get_work_hours(reference)


def _get_daily_clock_in_time(reference: datetime) -> time:
    preferred_clock_in = datetime.combine(reference.date(), config.PREFERRED_CLOCK_IN, tzinfo=config.TZ)
    seeded_random = random.Random(reference.date().isoformat())
    random_margin = timedelta(minutes=seeded_random.randint(-15, 15))
    return (preferred_clock_in + random_margin).time().replace(microsecond=0)


def _get_daily_clock_out_time(reference: datetime) -> time:
    preferred_clock_in_dt = datetime.combine(reference.date(), config.PREFERRED_CLOCK_IN, tzinfo=config.TZ)
    work_hours = _get_work_hours(reference)
    base_clock_out_dt = preferred_clock_in_dt + timedelta(hours=work_hours)
    seeded_random = random.Random(reference.date().isoformat() + '-out')
    random_margin = timedelta(minutes=seeded_random.randint(-15, 15))
    return (base_clock_out_dt + random_margin).time().replace(microsecond=0)


def get_fichaje_hours(reference: datetime | None = None) -> dict[str, time] | None:
    now = reference or datetime.now(config.TZ)
    if not is_working_day(now):
        return None

    clock_in_time = _get_daily_clock_in_time(now)
    clock_out_time = _get_daily_clock_out_time(now)
    return {'clock_in': clock_in_time, 'clock_out': clock_out_time}


async def esperar_hora(target_time: time) -> None:
    now = datetime.now(config.TZ)
    target = datetime.combine(now.date(), target_time, tzinfo=config.TZ)
    if target <= now:
        target += timedelta(days=1)
    seconds = max((target - now).total_seconds(), 0)
    await asyncio.sleep(seconds)


def format_seconds(total_seconds: float) -> str:
    remaining = max(int(total_seconds), 0)
    hours, remainder = divmod(remaining, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def seconds_until(target_time: time) -> float:
    now = datetime.now(config.TZ)
    target = datetime.combine(now.date(), target_time, tzinfo=config.TZ)
    return max((target - now).total_seconds(), 0)


def next_working_clock_in(reference: datetime) -> datetime:
    cursor = reference
    for _ in range(MAX_WORKDAY_LOOKAHEAD_DAYS):
        hours = get_fichaje_hours(cursor)
        if hours is not None:
            target = datetime.combine(cursor.date(), hours['clock_in'], tzinfo=config.TZ)
            if target > reference:
                return target
        cursor = datetime.combine((cursor + timedelta(days=1)).date(), time.min, tzinfo=config.TZ)
    raise RuntimeError(f'No se encontró un día laborable en los próximos {MAX_WORKDAY_LOOKAHEAD_DAYS} días.')
