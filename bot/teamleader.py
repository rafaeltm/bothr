from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import datetime, time, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import config

_STATE_TTL = timedelta(minutes=10)
_MAX_PUBLIC_ERROR_LENGTH = 300
_oauth_states_lock = threading.Lock()
_oauth_states: dict[str, datetime] = {}
_last_error_state = threading.local()
_STACK_TRACE_MARKERS = ('traceback', 'file "', 'line ')
_PUBLIC_ERROR_ALLOWED_PATTERN = re.compile(r'^[\w\s.,:;()\-_/!?]+$')


class TeamleaderError(RuntimeError):
    """Raised when Teamleader integration operations fail."""


def _sanitize_public_error(message: str, fallback: str) -> str:
    normalized = (message or '').strip()
    if not normalized:
        return fallback
    first_line = normalized.splitlines()[0].strip()
    if not first_line:
        return fallback
    lowered = first_line.lower()
    if any(marker in lowered for marker in _STACK_TRACE_MARKERS):
        return fallback
    if 'password' in lowered or 'secret' in lowered or 'token' in lowered or '://' in first_line:
        return fallback
    if not _PUBLIC_ERROR_ALLOWED_PATTERN.match(first_line):
        return fallback
    return first_line[:_MAX_PUBLIC_ERROR_LENGTH]


def _set_last_error_message(message: str, fallback: str) -> None:
    safe_message = _sanitize_public_error(message, fallback)
    _last_error_state.message = safe_message


def get_last_error_message(fallback: str) -> str:
    message = getattr(_last_error_state, 'message', None)
    _last_error_state.message = None
    return message or fallback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_ALLOWED_TEAMLEADER_HOSTNAMES = {
    'teamleader.eu',
    'app.teamleader.eu',
    'focus.teamleader.eu',
    'api.focus.teamleader.eu',
}


def _normalize_base_url(url: str | None, fallback: str) -> str:
    value = (url or fallback).strip().rstrip('/')
    parsed = urlparse(value)
    if parsed.scheme != 'https':
        raise TeamleaderError('La URL base de Teamleader debe usar el esquema https.')
    host = parsed.netloc.split(':')[0].lower()
    if host not in _ALLOWED_TEAMLEADER_HOSTNAMES and not host.endswith('.teamleader.eu'):
        raise TeamleaderError('La URL base de Teamleader debe ser un dominio oficial de Teamleader (teamleader.eu).')
    return value


def _parse_json_response(response_body: bytes) -> dict[str, Any]:
    if not response_body:
        return {}
    try:
        payload = json.loads(response_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeamleaderError('Respuesta inválida del API de Teamleader.') from exc
    if not isinstance(payload, dict):
        raise TeamleaderError('Respuesta inválida del API de Teamleader.')
    return payload


def _extract_error(payload: dict[str, Any], fallback: str) -> str:
    if 'error' in payload and payload['error']:
        return str(payload.get('error_description') or payload['error'])
    errors = payload.get('errors')
    if isinstance(errors, list) and errors:
        first_error = errors[0]
        if isinstance(first_error, dict):
            message = first_error.get('message') or first_error.get('title')
            if message:
                return str(message)
    return fallback


def _http_post(url: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    payload = json.dumps(body).encode('utf-8')
    request_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if headers:
        request_headers.update(headers)
    request = Request(url=url, data=payload, method='POST', headers=request_headers)
    try:
        # Safe: URLs are built from fixed defaults plus trusted operator config.
        with urlopen(request, timeout=20) as response:  # noqa: S310
            return _parse_json_response(response.read())
    except HTTPError as exc:
        response_payload = _parse_json_response(exc.read())
        message = _extract_error(response_payload, f'Error HTTP {exc.code} al contactar Teamleader.')
        _set_last_error_message(message, 'No se pudo completar la operación en Teamleader.')
        raise TeamleaderError(message) from exc
    except URLError as exc:
        message = 'No se pudo conectar con Teamleader.'
        _set_last_error_message(message, message)
        raise TeamleaderError(message) from exc


def _cleanup_expired_states() -> None:
    now = _utc_now()
    expired = [state for state, expires_at in _oauth_states.items() if expires_at <= now]
    for state in expired:
        _oauth_states.pop(state, None)


def build_authorization_url() -> str:
    if not config.TEAMLEADER_CLIENT_ID or not config.TEAMLEADER_REDIRECT_URI:
        raise TeamleaderError('Configura TEAMLEADER_CLIENT_ID y TEAMLEADER_REDIRECT_URI antes de conectar.')
    state = secrets.token_urlsafe(24)
    with _oauth_states_lock:
        _cleanup_expired_states()
        _oauth_states[state] = _utc_now() + _STATE_TTL
    query_params = urlencode(
        {
            'client_id': config.TEAMLEADER_CLIENT_ID,
            'redirect_uri': config.TEAMLEADER_REDIRECT_URI,
            'response_type': 'code',
            'state': state,
        }
    )
    auth_base_url = _normalize_base_url(config.TEAMLEADER_AUTH_BASE_URL, 'https://focus.teamleader.eu')
    return f'{auth_base_url}/oauth2/authorize?{query_params}'


def validate_oauth_state(state: str | None) -> bool:
    if not state:
        return False
    with _oauth_states_lock:
        _cleanup_expired_states()
        expires_at = _oauth_states.pop(state, None)
    return bool(expires_at and expires_at > _utc_now())


def _build_token_payload(grant_type: str, **kwargs: str) -> dict[str, Any]:
    if not config.TEAMLEADER_CLIENT_ID or not config.TEAMLEADER_CLIENT_SECRET:
        raise TeamleaderError('Configura TEAMLEADER_CLIENT_ID y TEAMLEADER_CLIENT_SECRET antes de conectar.')
    if not config.TEAMLEADER_REDIRECT_URI:
        raise TeamleaderError('Configura TEAMLEADER_REDIRECT_URI antes de conectar.')

    payload: dict[str, Any] = {
        'grant_type': grant_type,
        'client_id': config.TEAMLEADER_CLIENT_ID,
        'client_secret': config.TEAMLEADER_CLIENT_SECRET,
        'redirect_uri': config.TEAMLEADER_REDIRECT_URI,
    }
    payload.update(kwargs)
    return payload


def _to_expires_at(expires_in: Any) -> str:
    try:
        expires_seconds = int(expires_in)
    except (TypeError, ValueError):
        expires_seconds = 3600
    expires_at = _utc_now() + timedelta(seconds=max(0, expires_seconds))
    return expires_at.replace(microsecond=0).isoformat()


def _extract_token_values(payload: dict[str, Any]) -> dict[str, str]:
    access_token = payload.get('access_token')
    refresh_token = payload.get('refresh_token')
    if not access_token or not refresh_token:
        raise TeamleaderError(_extract_error(payload, 'No se recibieron tokens válidos de Teamleader.'))

    values = {
        'TEAMLEADER_ACCESS_TOKEN': str(access_token),
        'TEAMLEADER_REFRESH_TOKEN': str(refresh_token),
        'TEAMLEADER_TOKEN_EXPIRES_AT': _to_expires_at(payload.get('expires_in')),
    }
    account_id = payload.get('organization_id') or payload.get('account_id')
    if account_id:
        values['TEAMLEADER_ACCOUNT_ID'] = str(account_id)
    return values


def exchange_code_for_token(code: str) -> dict[str, str]:
    token_base_url = _normalize_base_url(config.TEAMLEADER_AUTH_BASE_URL, 'https://focus.teamleader.eu')
    payload = _build_token_payload('authorization_code', code=code)
    response = _http_post(f'{token_base_url}/oauth2/access_token', payload)
    return _extract_token_values(response)


def refresh_access_token() -> dict[str, str]:
    if not config.TEAMLEADER_REFRESH_TOKEN:
        raise TeamleaderError('No hay refresh token configurado para Teamleader.')
    token_base_url = _normalize_base_url(config.TEAMLEADER_AUTH_BASE_URL, 'https://focus.teamleader.eu')
    payload = _build_token_payload('refresh_token', refresh_token=config.TEAMLEADER_REFRESH_TOKEN)
    response = _http_post(f'{token_base_url}/oauth2/access_token', payload)
    return _extract_token_values(response)


def _parse_expires_at(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_valid_access_token() -> tuple[str, dict[str, str]]:
    if not config.TEAMLEADER_ACCESS_TOKEN:
        raise TeamleaderError('Conecta Teamleader antes de usar esta operación.')
    expires_at = _parse_expires_at(config.TEAMLEADER_TOKEN_EXPIRES_AT)
    if expires_at and expires_at <= _utc_now() + timedelta(seconds=60):
        refreshed_values = refresh_access_token()
        token = refreshed_values['TEAMLEADER_ACCESS_TOKEN']
        return token, refreshed_values
    return config.TEAMLEADER_ACCESS_TOKEN, {}


def api_call(method: str, payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    token, refresh_updates = ensure_valid_access_token()
    api_base_url = _normalize_base_url(config.TEAMLEADER_API_BASE_URL, 'https://api.focus.teamleader.eu')
    response = _http_post(
        f'{api_base_url}/{method.lstrip("/")}',
        payload or {},
        headers={'Authorization': 'Bearer ' + token},
    )
    return response, refresh_updates


def test_connection() -> tuple[dict[str, Any], dict[str, str]]:
    response, refresh_updates = api_call('users.me', {})
    return response, refresh_updates


def _to_datetime_str(date_str: str, end_of_day: bool = False) -> str:
    """Convert a YYYY-MM-DD date string to a full ISO 8601 datetime string.

    The Teamleader API requires datetime strings (not bare dates) for the
    ``started_after`` / ``started_before`` filter fields.  If the value already
    contains a time component it is returned unchanged.
    """
    if 'T' in date_str or ' ' in date_str:
        return date_str
    local_date = datetime.fromisoformat(date_str.strip()).date()
    local_time = time.max.replace(microsecond=0) if end_of_day else time.min
    return datetime.combine(local_date, local_time, tzinfo=config.TZ).isoformat()


def list_time_entries(started_after: str, started_before: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    page_size = config.TEAMLEADER_PAGE_SIZE
    task_type = str(config.TEAMLEADER_TASK_TYPE).strip()
    filters: dict[str, Any] = {
        'started_after': _to_datetime_str(started_after, end_of_day=False),
        'started_before': _to_datetime_str(started_before, end_of_day=True),
    }
    if config.TEAMLEADER_TASK_ID:
        filters['subject'] = {
            'type': task_type,
            'id': config.TEAMLEADER_TASK_ID,
        }
    entries: list[dict[str, Any]] = []
    refresh_updates: dict[str, str] = {}
    page_number = 1
    while True:
        payload = {
            'filter': filters,
            'sort': [
                {
                    'field': 'starts_on',
                    'order': 'asc',
                }
            ],
            'page': {
                'size': page_size,
                'number': page_number,
            },
        }
        response, page_refresh_updates = api_call('timeTracking.list', payload)
        refresh_updates.update(page_refresh_updates)
        data = response.get('data')
        if not isinstance(data, list):
            break
        page_entries = [entry for entry in data if isinstance(entry, dict)]
        entries.extend(page_entries)
        if len(page_entries) < page_size:
            break
        meta = response.get('meta')
        if not isinstance(meta, dict):
            break
        matches = meta.get('matches')
        if isinstance(matches, int) and len(entries) >= matches:
            break
        page_number += 1
    return entries, refresh_updates
