from __future__ import annotations

import asyncio
import logging
from datetime import time

from flask import Blueprint, jsonify, render_template, request

import config
from bot import telegram

settings_bp = Blueprint('settings', __name__)
MASK_VALUE = '***'
logger = logging.getLogger('bothr')



def _stringify_value(value):
    """Convert config values into .env-safe string representations."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return '' if value is None else str(value)



def _format_env_value(value: str) -> str:
    """Escape and quote values before writing them to the .env file."""
    if value == '':
        # Keep explicit empty assignments as KEY= (no quoting needed).
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
    """Rewrite the managed .env file using the canonical key order for this app."""
    lines = [f'{key}={_format_env_value(values.get(key, ""))}' for key in config.MANAGED_ENV_KEYS]
    config.ENV_FILE.write_text("\n".join(lines) + "\n", encoding='utf-8')
    config.ENV_FILE.chmod(0o600)



def _get_form_settings() -> dict[str, object]:
    return config.get_current_settings(mask_sensitive=True, mask=MASK_VALUE)


@settings_bp.get('/api/settings')
def get_settings():
    return jsonify(config.get_current_settings(mask_sensitive=True, mask=MASK_VALUE))


@settings_bp.post('/api/settings')
def save_settings():
    payload = request.get_json(silent=True) or {}
    current = {
        key: _stringify_value(config.get_current_settings(mask_sensitive=False).get(key, ''))
        for key in config.MANAGED_ENV_KEYS
    }

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


@settings_bp.post('/api/test-telegram')
def test_telegram():
    if not config.BOT_TOKEN or not config.CHAT_ID:
        return jsonify({'success': False, 'error': 'Configura BOT_TOKEN y CHAT_ID antes de probar Telegram.'}), 400

    try:
        asyncio.run(telegram.send_message(config.CHAT_ID, 'Mensaje de prueba enviado desde el dashboard de Bothr.'))
        return jsonify({'success': True})
    except Exception:
        logger.exception('No se pudo enviar el mensaje de prueba de Telegram.')
        return jsonify({'success': False, 'error': 'No se pudo enviar el mensaje de prueba.'}), 500


@settings_bp.get('/settings')
def settings_page():
    return render_template('settings.html', settings=_get_form_settings(), form_mask=MASK_VALUE)
