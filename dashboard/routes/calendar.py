from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

import config
from bot import scheduler
from dashboard.auth import auth

calendar_bp = Blueprint('calendar_bp', __name__)


def _validate_dates(values: object, field_name: str) -> tuple[list[str] | None, str | None]:
    """Validate YYYY-MM-DD strings and return (normalized_values, error_message)."""
    if not isinstance(values, list):
        return None, f'Formato inválido para {field_name}.'

    normalized: list[str] = []
    for raw_item in values:
        if not isinstance(raw_item, str):
            return None, f'Formato inválido para {field_name}: todos los elementos deben ser texto.'
        date_text = raw_item.strip()
        try:
            datetime.strptime(date_text, '%Y-%m-%d')
        except ValueError:
            return None, f'Fecha inválida en {field_name}: "{date_text}". Usa formato YYYY-MM-DD.'
        normalized.append(date_text)
    return normalized, None


@calendar_bp.get('/api/festivos')
@auth.login_required
def get_festivos():
    return jsonify({'festivos': sorted(config.load_festivos())})


@calendar_bp.post('/api/festivos')
@auth.login_required
def save_festivos():
    payload = request.get_json(silent=True) or {}
    festivos, error = _validate_dates(payload.get('festivos', []), 'festivos')
    if error:
        return jsonify({'success': False, 'error': error}), 400
    config.write_json_file(config.FESTIVOS_FILE, {'festivos': festivos})
    config.invalidate_calendar_cache()
    return jsonify({'success': True, 'festivos': festivos})


@calendar_bp.get('/api/jornada_reducida')
@auth.login_required
def get_jornada_reducida():
    return jsonify({'dias': sorted(config.load_jornada_reducida())})


@calendar_bp.post('/api/jornada_reducida')
@auth.login_required
def save_jornada_reducida():
    payload = request.get_json(silent=True) or {}
    dias, error = _validate_dates(payload.get('dias', []), 'jornada reducida')
    if error:
        return jsonify({'success': False, 'error': error}), 400
    config.write_json_file(config.JORNADA_REDUCIDA_FILE, {'dias': dias})
    config.invalidate_calendar_cache()
    return jsonify({'success': True, 'dias': dias})


@calendar_bp.get('/api/status')
@auth.login_required
def get_status():
    return jsonify(scheduler.get_status_payload())


@calendar_bp.get('/api/logs')
@auth.login_required
def get_logs():
    return jsonify({'lines': scheduler.tail_log_lines(100)})


@calendar_bp.post('/api/errors/mark-seen')
@auth.login_required
def mark_errors_as_seen():
    scheduler.mark_last_error_as_seen()
    return jsonify({'success': True})


@calendar_bp.get('/calendar')
@auth.login_required
def calendar_page():
    return render_template('calendar.html')


@calendar_bp.get('/logs')
@auth.login_required
def logs_page():
    return render_template('logs.html', status=scheduler.get_status_payload())
