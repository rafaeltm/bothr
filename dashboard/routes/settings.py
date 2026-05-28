from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import config
from bot import schedule, teamleader, telegram
from dashboard.auth import auth

settings_bp = Blueprint('settings', __name__)
MASK_VALUE = '***'
logger = logging.getLogger('bothr')


def _stringify_value(value: object) -> str:
    """Serialize in-memory setting values into .env-compatible strings."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return '' if value is None else str(value)


def _normalize_time_value(value: object) -> str | None:
    if value is None:
        return ''
    normalized = str(value).strip()
    if normalized == '':
        return ''
    try:
        parsed = time.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.strftime('%H:%M')


def _write_env_file(values: dict[str, str]) -> None:
    config.write_managed_env(values)


def _get_current_env_values() -> dict[str, str]:
    return {
        key: _stringify_value(config.get_current_settings(mask_sensitive=False).get(key, ''))
        for key in config.MANAGED_ENV_KEYS
    }


def _persist_settings_updates(updates: dict[str, object]) -> None:
    current = _get_current_env_values()
    for key, value in updates.items():
        if key not in current:
            continue
        if key in config.SENSITIVE_ENV_KEYS and value == MASK_VALUE:
            continue
        current[key] = _stringify_value(value).strip()
    _write_env_file(current)
    config.refresh(force_file_override=True)
    telegram.refresh_bot()


def _get_form_settings() -> dict[str, object]:
    return config.get_current_settings(mask_sensitive=True, mask=MASK_VALUE)


@settings_bp.get('/api/settings')
@auth.login_required
def get_settings():
    return jsonify(config.get_current_settings(mask_sensitive=True, mask=MASK_VALUE))


@settings_bp.post('/api/settings')
@auth.login_required
def save_settings():
    payload = request.get_json(silent=True) or {}
    current = _get_current_env_values()

    for key in config.MANAGED_ENV_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if key in config.SENSITIVE_ENV_KEYS and value == MASK_VALUE:
            continue
        if key == 'PREFERRED_CLOCK_IN':
            normalized = _normalize_time_value(value)
            if normalized is None:
                return jsonify({'success': False, 'error': 'La hora deseada de entrada debe tener formato HH:MM.'}), 400
            current[key] = normalized
            continue
        if key in {'TEAMLEADER_WORKDAY_START', 'TEAMLEADER_WORKDAY_END'}:
            normalized = _normalize_time_value(value)
            if normalized is None:
                field_name = (
                    'hora de inicio de jornada Teamleader'
                    if key == 'TEAMLEADER_WORKDAY_START'
                    else 'hora de fin de jornada Teamleader'
                )
                return jsonify({'success': False, 'error': f'La {field_name} debe tener formato HH:MM.'}), 400
            current[key] = normalized
            continue
        if key == 'TEAMLEADER_PAGE_SIZE':
            raw_value = '' if value is None else str(value).strip()
            if raw_value == '':
                current[key] = '100'
                continue
            try:
                parsed_size = int(raw_value)
            except ValueError:
                return jsonify({'success': False, 'error': 'TEAMLEADER_PAGE_SIZE debe ser un número entero entre 1 y 100.'}), 400
            if parsed_size < 1 or parsed_size > 100:
                return jsonify({'success': False, 'error': 'TEAMLEADER_PAGE_SIZE debe estar entre 1 y 100.'}), 400
            current[key] = str(parsed_size)
            continue
        if key == 'TEAMLEADER_TASK_TYPE':
            normalized_type = '' if value is None else str(value).strip()
            current[key] = normalized_type or str(config.TEAMLEADER_TASK_TYPE or 'nextgenTask')
            continue
        if isinstance(value, bool):
            current[key] = 'true' if value else 'false'
        elif value is None:
            current[key] = ''
        else:
            current[key] = str(value).strip()

    _write_env_file(current)
    config.refresh(force_file_override=True)
    telegram.refresh_bot()
    return jsonify({'success': True, 'settings': config.get_current_settings(mask_sensitive=True, mask=MASK_VALUE)})


def _redirect_teamleader_result(success: bool, message: str):
    status = 'success' if success else 'error'
    return redirect(url_for('settings.settings_page', teamleader_status=status, teamleader_message=message))


def _teamleader_disabled_response(redirect_on_error: bool = False):
    if config.TEAMLEADER_ENABLED:
        return None
    message = 'La integración de Teamleader está desactivada. Actívala en Configuración.'
    if redirect_on_error:
        return _redirect_teamleader_result(False, message)
    return jsonify({'success': False, 'error': message}), 400


@settings_bp.post('/api/integrations/teamleader/connect')
@auth.login_required
def teamleader_connect():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response
    try:
        auth_url = teamleader.build_authorization_url()
        return jsonify({'success': True, 'auth_url': auth_url})
    except teamleader.TeamleaderError:
        return jsonify({'success': False, 'error': 'No se pudo iniciar la conexión de Teamleader.'}), 400
    except Exception:
        logger.exception('No se pudo iniciar la conexión de Teamleader.')
        return jsonify({'success': False, 'error': 'No se pudo iniciar la conexión con Teamleader.'}), 500


@settings_bp.get('/api/integrations/teamleader/callback')
@auth.login_required
def teamleader_callback():
    disabled_response = _teamleader_disabled_response(redirect_on_error=True)
    if disabled_response:
        return disabled_response
    error = (request.args.get('error') or '').strip()
    if error:
        description = (request.args.get('error_description') or '').strip()
        message = description or f'Teamleader devolvió el error: {error}.'
        return _redirect_teamleader_result(False, message)

    if not teamleader.validate_oauth_state(request.args.get('state')):
        return _redirect_teamleader_result(False, 'Estado OAuth inválido o expirado. Inicia la conexión de nuevo.')

    code = (request.args.get('code') or '').strip()
    if not code:
        return _redirect_teamleader_result(False, 'No se recibió el código OAuth de Teamleader.')

    try:
        token_values = teamleader.exchange_code_for_token(code)
        _persist_settings_updates(token_values)
        return _redirect_teamleader_result(True, 'Cuenta Teamleader conectada correctamente.')
    except teamleader.TeamleaderError:
        return _redirect_teamleader_result(False, 'No se pudo completar la autenticación con Teamleader.')
    except Exception:
        logger.exception('No se pudo completar el callback OAuth de Teamleader.')
        return _redirect_teamleader_result(False, 'No se pudo completar la conexión de Teamleader.')


@settings_bp.post('/api/integrations/teamleader/disconnect')
@auth.login_required
def teamleader_disconnect():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response
    _persist_settings_updates(
        {
            'TEAMLEADER_ACCESS_TOKEN': '',
            'TEAMLEADER_REFRESH_TOKEN': '',
            'TEAMLEADER_TOKEN_EXPIRES_AT': '',
            'TEAMLEADER_ACCOUNT_ID': '',
        }
    )
    return jsonify({'success': True, 'settings': _get_form_settings()})


@settings_bp.post('/api/integrations/teamleader/test')
@auth.login_required
def teamleader_test():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response
    try:
        response, refresh_updates = teamleader.test_connection()
        if refresh_updates:
            _persist_settings_updates(refresh_updates)
        return jsonify(
            {
                'success': True,
                'message': 'Conexión con Teamleader verificada.',
                'settings': _get_form_settings(),
                'account': response.get('data', {}),
            }
        )
    except teamleader.TeamleaderError:
        return jsonify({'success': False, 'error': 'No se pudo verificar la conexión con Teamleader.'}), 400
    except Exception:
        logger.exception('No se pudo verificar la conexión con Teamleader.')
        return jsonify({'success': False, 'error': 'No se pudo verificar la conexión con Teamleader.'}), 500


def _parse_iso_date(raw_value: str) -> date:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError('empty')
    return date.fromisoformat(normalized)


@settings_bp.get('/api/integrations/teamleader/entries')
@auth.login_required
def teamleader_entries():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response
    from_param = (request.args.get('from') or '').strip()
    to_param = (request.args.get('to') or '').strip()
    if not from_param or not to_param:
        return jsonify({'success': False, 'error': 'Debes informar from y to en formato YYYY-MM-DD.'}), 400

    try:
        from_date = _parse_iso_date(from_param)
        to_date = _parse_iso_date(to_param)
    except ValueError:
        return jsonify({'success': False, 'error': 'from/to deben tener formato YYYY-MM-DD válido.'}), 400
    if to_date < from_date:
        return jsonify({'success': False, 'error': 'El rango de fechas es inválido.'}), 400

    try:
        entries, refresh_updates = teamleader.list_time_entries(from_date.isoformat(), to_date.isoformat())
        if refresh_updates:
            _persist_settings_updates(refresh_updates)
        return jsonify({'success': True, 'entries': entries, 'settings': _get_form_settings()})
    except teamleader.TeamleaderError as exc:
        logger.warning('Error al obtener fichajes de Teamleader: %s', exc)
        return jsonify(
            {
                'success': False,
                'error': teamleader.get_last_error_message('No se pudieron obtener los fichajes de Teamleader.'),
            }
        ), 400
    except Exception:
        logger.exception('No se pudieron obtener los fichajes de Teamleader.')
        return jsonify({'success': False, 'error': 'No se pudieron obtener los fichajes de Teamleader.'}), 500


def _extract_duration_seconds(entry: dict[str, object]) -> int:
    """Extract duration in seconds from Teamleader entries.

    Teamleader can return duration as either a plain number or a nested object
    with numeric `seconds`/`value` fields; missing, non-numeric, unsupported, or
    negative values return 0.
    """
    if not isinstance(entry, dict):
        return 0
    duration = entry.get('duration')
    if isinstance(duration, dict):
        raw_unit = str(duration.get('unit') or '').strip().lower()
        seconds_value = duration.get('seconds')
        if isinstance(seconds_value, (int, float)):
            return int(max(0, seconds_value))
        value = duration.get('value')
        if isinstance(value, (int, float)):
            normalized_value = max(0.0, float(value))
            if raw_unit in {'hour', 'hours', 'h'}:
                return int(normalized_value * 3600)
            if raw_unit in {'minute', 'minutes', 'min', 'm'}:
                return int(normalized_value * 60)
            if raw_unit in {'second', 'seconds', 'sec', 's'}:
                return int(normalized_value)
            if raw_unit:
                logger.warning('Unidad de duración Teamleader no reconocida: %s', raw_unit)
                return 0
            return int(normalized_value)
    if isinstance(duration, (int, float)):
        return int(max(0, duration))
    return 0


def _sum_entry_durations(entries: list[dict[str, object]]) -> int:
    return sum(_extract_duration_seconds(entry) for entry in entries)


def _parse_hhmm(raw_value: str) -> time:
    parsed = time.fromisoformat(raw_value.strip())
    return parsed.replace(second=0, microsecond=0)


def _get_teamleader_entries(from_date: date, to_date: date) -> list[dict[str, object]]:
    entries, refresh_updates = teamleader.list_time_entries(from_date.isoformat(), to_date.isoformat())
    if refresh_updates:
        _persist_settings_updates(refresh_updates)
    return entries


def _resolve_teamleader_period(period: str, today: date) -> tuple[str, date, date]:
    normalized = period.strip().lower()
    if normalized == 'daily':
        return 'Hoy', today, today
    if normalized == 'weekly':
        from_date = today - timedelta(days=today.weekday())
        return 'Esta semana', from_date, from_date + timedelta(days=6)
    if normalized == 'monthly':
        from_date = today.replace(day=1)
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        return 'Este mes', from_date, next_month - timedelta(days=1)
    raise ValueError('invalid-period')


def _resolve_next_teamleader_preview(today: date, has_today_entry: bool) -> dict[str, object]:
    try:
        workday_start = _parse_hhmm(config.TEAMLEADER_WORKDAY_START)
    except (TypeError, ValueError):
        workday_start = time(hour=8, minute=0)

    if has_today_entry:
        target_date = today + timedelta(days=1)
    else:
        target_date = today

    for _ in range(schedule.MAX_WORKDAY_LOOKAHEAD_DAYS):
        target_reference = datetime.combine(target_date, time.min, tzinfo=config.TZ)
        if schedule.is_working_day(target_reference):
            work_hours = schedule.get_work_hours(target_reference)
            duration_seconds = int(work_hours * 3600)
            started_at = datetime.combine(target_date, workday_start, tzinfo=config.TZ)
            return {
                'date': target_date.isoformat(),
                'hours': work_hours,
                'duration_seconds': duration_seconds,
                'started_at': started_at.isoformat(),
            }
        target_date += timedelta(days=1)

    return {}


@settings_bp.get('/api/integrations/teamleader/analysis')
@auth.login_required
def teamleader_analysis():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response
    from_param = (request.args.get('from') or '').strip()
    to_param = (request.args.get('to') or '').strip()
    if not from_param or not to_param:
        return jsonify({'success': False, 'error': 'Debes informar from y to en formato YYYY-MM-DD.'}), 400

    try:
        from_date = _parse_iso_date(from_param)
        to_date = _parse_iso_date(to_param)
    except ValueError:
        return jsonify({'success': False, 'error': 'from/to deben tener formato YYYY-MM-DD válido.'}), 400
    if to_date < from_date:
        return jsonify({'success': False, 'error': 'El rango de fechas es inválido.'}), 400

    try:
        exact_start = _parse_hhmm(config.TEAMLEADER_WORKDAY_START)
        exact_end = _parse_hhmm(config.TEAMLEADER_WORKDAY_END)
    except (TypeError, ValueError):
        return jsonify(
            {
                'success': False,
                'error': 'Configura TEAMLEADER_WORKDAY_START y TEAMLEADER_WORKDAY_END en formato HH:MM.',
            }
        ), 400

    expected_daily_seconds = int(
        (
            datetime.combine(datetime.min, exact_end)
            - datetime.combine(datetime.min, exact_start)
        ).total_seconds()
    )
    if expected_daily_seconds <= 0:
        return jsonify({'success': False, 'error': 'La jornada exacta debe tener fin posterior al inicio.'}), 400

    try:
        entries, refresh_updates = teamleader.list_time_entries(from_date.isoformat(), to_date.isoformat())
        if refresh_updates:
            _persist_settings_updates(refresh_updates)
        total_clocked_seconds = sum(_extract_duration_seconds(entry) for entry in entries)
        working_days = sum(
            1
            for day_offset in range((to_date - from_date).days + 1)
            if schedule.is_working_day(
                datetime.combine(
                    from_date + timedelta(days=day_offset),
                    time.min,
                    tzinfo=config.TZ,
                )
            )
        )
        expected_total_seconds = max(0, working_days * expected_daily_seconds)
        return jsonify(
            {
                'success': True,
                'analysis': {
                    'working_days': working_days,
                    'expected_daily_seconds': expected_daily_seconds,
                    'expected_total_seconds': expected_total_seconds,
                    'clocked_total_seconds': total_clocked_seconds,
                    'balance_seconds': total_clocked_seconds - expected_total_seconds,
                },
                'entries_count': len(entries),
                'settings': _get_form_settings(),
            }
        )
    except teamleader.TeamleaderError as exc:
        logger.warning('Error al calcular análisis de Teamleader: %s', exc)
        return jsonify(
            {
                'success': False,
                'error': teamleader.get_last_error_message('No se pudo calcular el análisis de horas de Teamleader.'),
            }
        ), 400
    except Exception:
        logger.exception('No se pudo calcular el análisis de horas de Teamleader.')
        return jsonify({'success': False, 'error': 'No se pudo calcular el análisis de horas de Teamleader.'}), 500


@settings_bp.get('/api/integrations/teamleader/dashboard-summary')
@auth.login_required
def teamleader_dashboard_summary():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response

    today = datetime.now(config.TZ).date()
    period = (request.args.get('period') or 'daily').strip().lower()

    try:
        period_label, from_date, to_date = _resolve_teamleader_period(period, today)
    except ValueError:
        return jsonify({'success': False, 'error': 'El periodo debe ser daily, weekly o monthly.'}), 400

    try:
        period_entries = _get_teamleader_entries(from_date, to_date)
        today_entries = period_entries if from_date == today and to_date == today else _get_teamleader_entries(today, today)
        has_today_entry = len(today_entries) > 0
        return jsonify(
            {
                'success': True,
                'summary': {
                    'period': period,
                    'period_label': period_label,
                    'from': from_date.isoformat(),
                    'to': to_date.isoformat(),
                    'entries_count': len(period_entries),
                    'total_seconds': _sum_entry_durations(period_entries),
                    'has_today_entry': has_today_entry,
                    'today_entries_count': len(today_entries),
                    'today_total_seconds': _sum_entry_durations(today_entries),
                    'next_entry_preview': _resolve_next_teamleader_preview(today, has_today_entry),
                },
                'settings': _get_form_settings(),
            }
        )
    except teamleader.TeamleaderError as exc:
        logger.warning('Error al obtener resumen de Teamleader para dashboard: %s', exc)
        return jsonify(
            {
                'success': False,
                'error': teamleader.get_last_error_message('No se pudo obtener el resumen de Teamleader.'),
            }
        ), 400
    except Exception:
        logger.exception('No se pudo obtener el resumen de Teamleader para dashboard.')
        return jsonify({'success': False, 'error': 'No se pudo obtener el resumen de Teamleader.'}), 500


@settings_bp.post('/api/integrations/teamleader/add-entry')
@auth.login_required
def teamleader_add_entry():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response

    body = request.get_json(silent=True) or {}
    date_param = (body.get('date') or '').strip()
    hours_param = body.get('hours')
    description_param = (body.get('description') or '').strip() or None

    today = datetime.now(config.TZ).date()
    if date_param:
        try:
            entry_date = _parse_iso_date(date_param)
        except ValueError:
            return jsonify({'success': False, 'error': 'date debe tener formato YYYY-MM-DD válido.'}), 400
    else:
        entry_date = today

    if hours_param is not None:
        try:
            hours_value = float(hours_param)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'hours debe ser un número.'}), 400
        if hours_value <= 0:
            return jsonify({'success': False, 'error': 'hours debe ser mayor que cero.'}), 400
    else:
        # Default: 7h on Fridays (jornada reducida), 9h otherwise
        _FRIDAY = 4
        _HOURS_FRIDAY = 7.0
        _HOURS_NORMAL = 9.0
        hours_value = _HOURS_FRIDAY if entry_date.weekday() == _FRIDAY else _HOURS_NORMAL

    duration_seconds = int(hours_value * 3600)

    try:
        workday_start = _parse_hhmm(config.TEAMLEADER_WORKDAY_START)
    except (TypeError, ValueError):
        return jsonify(
            {'success': False, 'error': 'Configura TEAMLEADER_WORKDAY_START en formato HH:MM.'}
        ), 400

    started_at = datetime.combine(entry_date, workday_start, tzinfo=config.TZ)

    subject_id = (config.TEAMLEADER_TASK_ID or '').strip() or None
    subject_type = (config.TEAMLEADER_TASK_TYPE or 'nextgenTask').strip()
    user_id = (config.TEAMLEADER_USER_ID or '').strip() or None

    try:
        response, refresh_updates = teamleader.add_time_entry(
            started_at=started_at,
            duration_seconds=duration_seconds,
            subject_id=subject_id,
            subject_type=subject_type,
            description=description_param,
            user_id=user_id,
        )
        if refresh_updates:
            _persist_settings_updates(refresh_updates)
        entry_data = response.get('data') or {}
        entry_id = entry_data.get('id') if isinstance(entry_data, dict) else None
        return jsonify(
            {
                'success': True,
                'entry_id': entry_id,
                'date': entry_date.isoformat(),
                'hours': hours_value,
                'started_at': started_at.isoformat(),
                'settings': _get_form_settings(),
            }
        )
    except teamleader.TeamleaderError as exc:
        logger.warning('Error al añadir registro en Teamleader: %s', exc)
        return jsonify(
            {
                'success': False,
                'error': teamleader.get_last_error_message('No se pudo añadir el registro en Teamleader.'),
            }
        ), 400
    except Exception:
        logger.exception('No se pudo añadir el registro en Teamleader.')
        return jsonify({'success': False, 'error': 'No se pudo añadir el registro en Teamleader.'}), 500


@settings_bp.get('/api/integrations/teamleader/available-tasks')
@auth.login_required
def teamleader_available_tasks():
    disabled_response = _teamleader_disabled_response()
    if disabled_response:
        return disabled_response
    try:
        tasks, refresh_updates = teamleader.list_tasks()
        if refresh_updates:
            _persist_settings_updates(refresh_updates)
        task_list = [
            {
                'id': str(t.get('id') or '').strip(),
                'title': str(t.get('title') or t.get('summary') or t.get('name') or '').strip(),
                'type': 'nextgenTask',
            }
            for t in tasks
            if str(t.get('id') or '').strip()
        ]
        return jsonify({'success': True, 'tasks': task_list})
    except teamleader.TeamleaderError as exc:
        logger.warning('Error al obtener tareas de Teamleader: %s', exc)
        return jsonify(
            {
                'success': False,
                'error': teamleader.get_last_error_message('No se pudieron obtener las tareas de Teamleader.'),
            }
        ), 400
    except Exception:
        logger.exception('No se pudieron obtener las tareas de Teamleader.')
        return jsonify({'success': False, 'error': 'No se pudieron obtener las tareas de Teamleader.'}), 500


@settings_bp.get('/api/integrations/teamleader/task-schedules')
@auth.login_required
def get_task_schedules():
    return jsonify({'success': True, 'schedules': config.read_task_schedules()})


@settings_bp.post('/api/integrations/teamleader/task-schedules')
@auth.login_required
def save_task_schedules():
    body = request.get_json(silent=True)
    if not isinstance(body, list):
        return jsonify({'success': False, 'error': 'Se esperaba un array JSON de registros de tareas.'}), 400

    validated: list[dict] = []
    for idx, item in enumerate(body):
        if not isinstance(item, dict):
            return jsonify({'success': False, 'error': f'El elemento en posición {idx} no es un objeto válido.'}), 400
        task_id = str(item.get('task_id') or '').strip()
        if not task_id:
            return jsonify({'success': False, 'error': f'El elemento en posición {idx} no tiene task_id.'}), 400
        start_time = str(item.get('start_time') or '').strip()
        end_time = str(item.get('end_time') or '').strip()
        if not start_time or not end_time:
            return jsonify(
                {'success': False, 'error': f'El elemento en posición {idx} debe incluir start_time y end_time.'}
            ), 400
        normalized_start = _normalize_time_value(start_time)
        if normalized_start is None:
            return jsonify({'success': False, 'error': f'start_time en posición {idx} debe tener formato HH:MM.'}), 400
        normalized_end = _normalize_time_value(end_time)
        if normalized_end is None:
            return jsonify({'success': False, 'error': f'end_time en posición {idx} debe tener formato HH:MM.'}), 400
        parsed_start = time.fromisoformat(normalized_start)
        parsed_end = time.fromisoformat(normalized_end)
        if parsed_end <= parsed_start:
            return jsonify(
                {'success': False, 'error': f'El elemento en posición {idx} debe tener end_time mayor que start_time.'}
            ), 400
        start_time = normalized_start
        end_time = normalized_end
        validated.append({
            'task_id': task_id,
            'task_name': str(item.get('task_name') or '').strip(),
            'task_type': str(item.get('task_type') or 'nextgenTask').strip(),
            'start_time': start_time,
            'end_time': end_time,
        })

    config.write_task_schedules(validated)
    return jsonify({'success': True, 'schedules': validated})


@settings_bp.post('/api/test-telegram')
@auth.login_required
def test_telegram():
    if not config.BOT_TOKEN or not config.CHAT_ID:
        return jsonify({'success': False, 'error': 'Configura BOT_TOKEN y CHAT_ID antes de probar Telegram.'}), 400

    try:
        telegram.send_message_sync(config.CHAT_ID, 'Mensaje de prueba enviado desde el dashboard de Bothr.')
        return jsonify({'success': True})
    except Exception:
        logger.exception('No se pudo enviar el mensaje de prueba de Telegram.')
        return jsonify({'success': False, 'error': 'No se pudo enviar el mensaje de prueba.'}), 500


@settings_bp.get('/settings')
@auth.login_required
def settings_page():
    status = (request.args.get('teamleader_status') or '').strip().lower()
    message = (request.args.get('teamleader_message') or '').strip()
    integration_feedback = None
    if status in {'success', 'error'} and message:
        integration_feedback = {'status': status, 'message': message}
    return render_template(
        'settings.html',
        settings=_get_form_settings(),
        form_mask=MASK_VALUE,
        integration_feedback=integration_feedback,
    )
