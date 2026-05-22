from __future__ import annotations

import json

from flask import Blueprint, jsonify, render_template, request

import config
from bot import scheduler
from dashboard.app import auth

calendar_bp = Blueprint('calendar_bp', __name__)



def _write_calendar_file(path, payload):
    config.ensure_parent(path)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


@calendar_bp.get('/api/festivos')
@auth.login_required
def get_festivos():
    return jsonify({'festivos': sorted(config.load_festivos())})


@calendar_bp.post('/api/festivos')
@auth.login_required
def save_festivos():
    payload = request.get_json(silent=True) or {}
    festivos = payload.get('festivos', [])
    if not isinstance(festivos, list):
        return jsonify({'success': False, 'error': 'Formato inválido para festivos.'}), 400
    _write_calendar_file(config.FESTIVOS_FILE, {'festivos': festivos})
    return jsonify({'success': True, 'festivos': festivos})


@calendar_bp.get('/api/jornada_reducida')
@auth.login_required
def get_jornada_reducida():
    return jsonify({'dias': sorted(config.load_jornada_reducida())})


@calendar_bp.post('/api/jornada_reducida')
@auth.login_required
def save_jornada_reducida():
    payload = request.get_json(silent=True) or {}
    dias = payload.get('dias', [])
    if not isinstance(dias, list):
        return jsonify({'success': False, 'error': 'Formato inválido para jornada reducida.'}), 400
    _write_calendar_file(config.JORNADA_REDUCIDA_FILE, {'dias': dias})
    return jsonify({'success': True, 'dias': dias})


@calendar_bp.get('/api/status')
@auth.login_required
def get_status():
    return jsonify(scheduler.get_status_payload())


@calendar_bp.get('/api/logs')
@auth.login_required
def get_logs():
    return jsonify({'lines': scheduler.tail_log_lines(100)})


@calendar_bp.get('/calendar')
@auth.login_required
def calendar_page():
    return render_template('calendar.html')


@calendar_bp.get('/logs')
@auth.login_required
def logs_page():
    return render_template('logs.html', status=scheduler.get_status_payload())
