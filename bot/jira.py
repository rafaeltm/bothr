from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import config

_ALLOWED_TEMPO_HOSTNAMES = {
    'api.tempo.io',
    'tempo.io',
}


class JiraError(RuntimeError):
    """Raised when Jira/Tempo integration operations fail."""


def _normalize_base_url(url: str | None, fallback: str) -> str:
    value = (url or fallback).strip().rstrip('/')
    parsed = urlparse(value)
    if parsed.scheme != 'https':
        raise JiraError('La URL base de Tempo debe usar el esquema https.')
    host = parsed.netloc.split(':')[0].lower()
    if host not in _ALLOWED_TEMPO_HOSTNAMES and not host.endswith('.tempo.io'):
        raise JiraError('La URL base de Tempo debe ser un dominio oficial de Tempo (tempo.io).')
    return value


def _parse_json_response(response_body: bytes) -> dict[str, Any]:
    if not response_body:
        return {}
    try:
        payload = json.loads(response_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JiraError('Respuesta inválida de la API de Tempo.') from exc
    if not isinstance(payload, dict):
        raise JiraError('Respuesta inválida de la API de Tempo.')
    return payload


def _extract_error(payload: dict[str, Any], fallback: str) -> str:
    message = payload.get('message') or payload.get('error') or payload.get('errorMessage')
    if message:
        return str(message)
    errors = payload.get('errors')
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            msg = first.get('message')
            if msg:
                return str(msg)
    return fallback


def _http_get(url: str, token: str) -> dict[str, Any]:
    request_headers = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
    }
    req = Request(url=url, method='GET', headers=request_headers)
    try:
        # Safe: URLs are built from fixed defaults plus trusted operator config.
        with urlopen(req, timeout=20) as response:  # noqa: S310
            return _parse_json_response(response.read())
    except HTTPError as exc:
        response_payload = _parse_json_response(exc.read())
        message = _extract_error(response_payload, f'Error HTTP {exc.code} al contactar Tempo.')
        raise JiraError(message) from exc
    except URLError as exc:
        raise JiraError('No se pudo conectar con Tempo.') from exc


def _get_token() -> str:
    if not config.JIRA_TEMPO_API_TOKEN:
        raise JiraError('Configura JIRA_TEMPO_API_TOKEN antes de usar esta operación.')
    return config.JIRA_TEMPO_API_TOKEN


def test_connection() -> dict[str, Any]:
    """Verify Tempo API credentials by retrieving the current user's info."""
    token = _get_token()
    base_url = _normalize_base_url(config.JIRA_TEMPO_BASE_URL, 'https://api.tempo.io')
    return _http_get(f'{base_url}/4/myself', token)


def list_worklogs(from_date: str, to_date: str, issue_key: str | None = None) -> list[dict[str, Any]]:
    """Return Tempo worklogs for the authenticated user in [from_date, to_date].

    Both dates must be YYYY-MM-DD strings.  If issue_key is provided only worklogs
    for that Jira issue are returned.  Pagination is handled automatically.
    """
    token = _get_token()
    base_url = _normalize_base_url(config.JIRA_TEMPO_BASE_URL, 'https://api.tempo.io')

    results: list[dict[str, Any]] = []
    limit = 50
    offset = 0

    while True:
        params: dict[str, object] = {
            'from': from_date,
            'to': to_date,
            'limit': limit,
            'offset': offset,
        }
        if issue_key:
            params['issue'] = issue_key
        url = f'{base_url}/4/worklogs?{urlencode(params)}'
        payload = _http_get(url, token)

        results_page = payload.get('results')
        if not isinstance(results_page, list):
            break
        results.extend(entry for entry in results_page if isinstance(entry, dict))

        metadata = payload.get('metadata') or {}
        next_offset = metadata.get('next')
        if next_offset is None:
            # No more pages
            break
        offset = next_offset

    return results
