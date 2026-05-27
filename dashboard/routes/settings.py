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


def _format_env_value(value: str) -> str:
    if value == '':
        return ''
    needs_quotes = any(char.isspace() for char in value) or '#' in value or '"' in value
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    if needs_quotes:
        return f'"{escaped}"'
    return escaped


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
    lines = [f'{key}={_format_env_value(values.get(key, ""))}' for key in config.MANAGED_ENV_KEYS]
    config.ENV_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    config.ENV_FILE.chmod(0o600)


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
            current[key] = normalized_type
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
        value = duration.get('seconds') or duration.get('value')
        if isinstance(value, (int, float)):
            return int(max(0, value))
    if isinstance(duration, (int, float)):
        return int(max(0, duration))
    return 0


def _parse_hhmm(raw_value: str) -> time:
    parsed = time.fromisoformat(raw_value.strip())
    return parsed.replace(second=0, microsecond=0)


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
