from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import TypedDict

import config
from bot import fichaje
from bot import logs as scheduler_logs
from bot import schedule, state, teamleader
from playwright.async_api import async_playwright

scheduler_logs.setup_logger()


def get_fichaje_hours(reference: datetime | None = None) -> dict[str, time] | None:
    return schedule.get_fichaje_hours(reference)


def mark_last_error_as_seen() -> None:
    scheduler_logs.mark_last_error_as_seen()


def tail_log_lines(limit: int = 100) -> list[str]:
    return scheduler_logs.tail_log_lines(limit)


def get_status_payload() -> dict[str, object]:
    now = datetime.now(config.TZ)
    hours = schedule.get_fichaje_hours(now)
    today = state.get_today_fichajes()
    today_clocked_in_at = today['entrada']
    today_clocked_out_at = today['salida']
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
        'last_error': scheduler_logs.get_visible_last_error(),
    }

    if schedule.es_festivo(now) or hours is None:
        try:
            next_working_entry = schedule.next_working_clock_in(now)
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
            'time_remaining': schedule.format_seconds((next_working_entry - now).total_seconds()),
        }

    if not today_clocked_in:
        target = datetime.combine(now.date(), hours['clock_in'], tzinfo=config.TZ)
        return {
            **base_payload,
            'next_action': 'entrada',
            'next_action_at': target.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': schedule.format_seconds(schedule.seconds_until(hours['clock_in'])),
        }

    if not today_clocked_out:
        target = datetime.combine(now.date(), hours['clock_out'], tzinfo=config.TZ)
        return {
            **base_payload,
            'next_action': 'salida',
            'next_action_at': target.strftime('%Y-%m-%d %H:%M:%S'),
            'time_remaining': schedule.format_seconds(schedule.seconds_until(hours['clock_out'])),
        }

    try:
        next_working_entry = schedule.next_working_clock_in(now)
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
        'time_remaining': schedule.format_seconds((next_working_entry - now).total_seconds()),
    }


async def _perform_fichaje(tipo: str) -> bool:
    async with async_playwright() as playwright:
        page, browser = await fichaje.login(playwright)
        if not page or not browser:
            return False
        try:
            success = await fichaje.fichar(page, tipo)
            if success:
                state.write_fichaje_log(tipo, datetime.now(config.TZ).strftime('%Y-%m-%d %H:%M:%S'))
                scheduler_logs.log_event(f'Fichaje de {tipo} completado.')
                await scheduler_logs.notify_telegram(f'Fichaje de {tipo} completado.')
                if tipo == 'entrada':
                    await _auto_teamleader_entry()
            return success
        finally:
            await browser.close()


async def _auto_teamleader_entry() -> None:
    """Create a Teamleader time entry automatically after a successful entrada fichaje."""
    config.refresh()
    if not config.TEAMLEADER_ENABLED or not config.TEAMLEADER_AUTO_ENTRY:
        return
    try:
        now = datetime.now(config.TZ)
        today_iso = now.date().isoformat()
        today_entries, refresh_updates = teamleader.list_time_entries(
            today_iso,
            today_iso,
            apply_task_filter=False,
        )
        if refresh_updates:
            config.persist_token_updates(refresh_updates)
        if today_entries:
            scheduler_logs.log_event('Registro automático en Teamleader omitido: ya existe un fichaje para hoy.')
            return

        user_id = (config.TEAMLEADER_USER_ID or '').strip() or None
        scheduled_entries = _resolve_scheduled_teamleader_entries(now.date())
        if scheduled_entries:
            total_duration_seconds = 0
            for scheduled_entry in scheduled_entries:
                _, refresh_updates = teamleader.add_time_entry(
                    started_at=scheduled_entry['started_at'],
                    duration_seconds=scheduled_entry['duration_seconds'],
                    subject_id=scheduled_entry['subject_id'],
                    subject_type=scheduled_entry['subject_type'],
                    user_id=user_id,
                )
                if refresh_updates:
                    config.persist_token_updates(refresh_updates)
                total_duration_seconds += scheduled_entry['duration_seconds']
            msg = (
                'Registros Teamleader añadidos automáticamente: '
                f"{now.date().isoformat()} · {len(scheduled_entries)} tarea(s) · "
                f'{total_duration_seconds / 3600:.2f}h.'
            )
            scheduler_logs.log_event(msg)
            await scheduler_logs.notify_telegram(msg)
            return

        yesterday = (now - timedelta(days=1)).date().isoformat()
        yesterday_entries, refresh_updates = teamleader.list_time_entries(
            yesterday,
            yesterday,
            apply_task_filter=False,
        )
        if refresh_updates:
            config.persist_token_updates(refresh_updates)

        work_hours = schedule._get_work_hours(now)
        duration_seconds = int(work_hours * 3600)
        raw_start = config.TEAMLEADER_WORKDAY_START
        workday_start = time.fromisoformat(raw_start.strip()).replace(second=0, microsecond=0)
        started_at = datetime.combine(now.date(), workday_start, tzinfo=config.TZ)
        subject_id = (config.TEAMLEADER_TASK_ID or '').strip() or None
        subject_type = (config.TEAMLEADER_TASK_TYPE or 'nextgenTask').strip()
        # Entries are sorted ascending by starts_on in Teamleader list API, so
        # reverse to check the most recent one first. If no subject is found,
        # configured values are used.
        for entry in reversed(yesterday_entries):
            if user_id and teamleader.extract_entry_user_id(entry) != user_id:
                continue
            previous_subject_id, previous_subject_type = teamleader.extract_entry_subject(entry)
            if not previous_subject_id:
                continue
            subject_id = previous_subject_id
            if previous_subject_type:
                subject_type = previous_subject_type
            scheduler_logs.log_event(
                f'Registro automático Teamleader: usando tarea del día anterior ({subject_type}:{subject_id}).'
            )
            break
        if not subject_id:
            msg = (
                'Registro automático Teamleader omitido: configura TEAMLEADER_TASK_ID '
                'o define tareas programadas con ID.'
            )
            scheduler_logs.log_event(msg, level=logging.WARNING)
            await scheduler_logs.notify_telegram(msg)
            return
        _, refresh_updates = teamleader.add_time_entry(
            started_at=started_at,
            duration_seconds=duration_seconds,
            subject_id=subject_id,
            subject_type=subject_type,
            user_id=user_id,
        )
        if refresh_updates:
            config.persist_token_updates(refresh_updates)
        msg = f'Registro Teamleader añadido automáticamente: {now.date().isoformat()} · {work_hours}h.'
        scheduler_logs.log_event(msg)
        await scheduler_logs.notify_telegram(msg)
    except Exception as exc:
        scheduler_logs.log_event(f'Error al añadir registro automático en Teamleader: {exc}', level=logging.WARNING)
        await scheduler_logs.notify_telegram(f'Error al añadir registro automático en Teamleader: {exc}')


def _parse_schedule_time(raw_value: str) -> time | None:
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        parsed = time.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(second=0, microsecond=0)


class _ResolvedTeamleaderEntry(TypedDict):
    started_at: datetime
    duration_seconds: int
    subject_id: str
    subject_type: str


def _resolve_scheduled_teamleader_entries(entry_date: date) -> list[_ResolvedTeamleaderEntry]:
    schedules = config.read_task_schedules()
    entries: list[_ResolvedTeamleaderEntry] = []
    for schedule_entry in schedules:
        task_id = str(schedule_entry.get('task_id') or '').strip()
        if not task_id:
            continue
        start_time = _parse_schedule_time(str(schedule_entry.get('start_time') or ''))
        end_time = _parse_schedule_time(str(schedule_entry.get('end_time') or ''))
        if not start_time or not end_time:
            scheduler_logs.log_event(
                f'Registro automático Teamleader: tarea omitida por horas inválidas ({task_id}).',
                level=logging.WARNING,
            )
            continue
        started_at = datetime.combine(entry_date, start_time, tzinfo=config.TZ)
        ended_at = datetime.combine(entry_date, end_time, tzinfo=config.TZ)
        if ended_at == started_at:
            scheduler_logs.log_event(
                f'Registro automático Teamleader: tarea omitida por rango horario sin duración ({task_id}).',
                level=logging.WARNING,
            )
            continue
        # Allow schedules that cross midnight (e.g. 23:00 -> 02:00).
        if ended_at < started_at:
            ended_at += timedelta(days=1)
        entries.append(
            {
                'started_at': started_at,
                'duration_seconds': int((ended_at - started_at).total_seconds()),
                'subject_id': task_id,
                'subject_type': str(schedule_entry.get('task_type') or 'nextgenTask').strip() or 'nextgenTask',
            }
        )
    entries.sort(key=lambda item: item['started_at'])
    return entries


async def run() -> None:
    scheduler_logs.log_event('Scheduler iniciado.')
    while True:
        try:
            now = datetime.now(config.TZ)
            hours = schedule.get_fichaje_hours(now)

            if schedule.es_festivo(now) or hours is None:
                scheduler_logs.log_event('Hoy no es laborable. Esperando al siguiente día.')
                await schedule.esperar_hora(time.min)
                continue

            if not state.es_fichaje_realizado_hoy('entrada'):
                scheduler_logs.log_event(f"Esperando fichaje de entrada a las {hours['clock_in'].strftime('%H:%M:%S')}.")
                await schedule.esperar_hora(hours['clock_in'])
                if not state.es_fichaje_realizado_hoy('entrada') and not schedule.es_festivo():
                    if not await _perform_fichaje('entrada'):
                        await asyncio.sleep(60)
                continue

            if not state.es_fichaje_realizado_hoy('salida'):
                scheduler_logs.log_event(f"Esperando fichaje de salida a las {hours['clock_out'].strftime('%H:%M:%S')}.")
                await schedule.esperar_hora(hours['clock_out'])
                if not state.es_fichaje_realizado_hoy('salida') and not schedule.es_festivo():
                    if not await _perform_fichaje('salida'):
                        await asyncio.sleep(60)
                continue

            scheduler_logs.log_event('Entrada y salida ya registradas hoy. Esperando al siguiente día.')
            await schedule.esperar_hora(time.min)
        except Exception as exc:
            scheduler_logs.log_event(f'Error no controlado en scheduler: {exc}', level=logging.ERROR)
            await scheduler_logs.notify_telegram(f'Error no controlado en scheduler: {exc}')
            await asyncio.sleep(60)
