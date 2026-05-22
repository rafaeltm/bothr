from __future__ import annotations

import asyncio
import logging

from flask import Blueprint, jsonify, render_template, request

import config
from bot import telegram
from dashboard.app import auth

settings_bp = Blueprint('settings', __name__)
MASK_VALUE = '***'
logger = logging.getLogger('bothr')



def _stringify_value(value):
    """Convert config values to strings suitable for .env persistence."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return '' if value is None else str(value)



def _format_env_value(value: str) -> str:
    """Escape and quote values before writing them to the .env file."""
    if value == '':
        return ''
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    if any(char.isspace() for char in value) or '#' in value or '"' in value:
        return f'"{escaped}"'
    return escaped



def _write_env_file(values: dict[str, str]) -> None:
    """Rewrite the managed .env file using the canonical key order for this app."""
    lines = [f'{key}={_format_env_value(values.get(key, ""))}' for key in config.MANAGED_ENV_KEYS]
    config.ENV_FILE.write_text("\n".join(lines) + "\n", encoding='utf-8')
    config.ENV_FILE.chmod(0o600)



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
@auth.login_required
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
@auth.login_required
def settings_page():
    return render_template('settings.html', settings=_get_form_settings(), form_mask=MASK_VALUE)
