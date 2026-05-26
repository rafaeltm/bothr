from __future__ import annotations

import json
import re
from datetime import datetime

import config

DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
# Supports timestamps like YYYY-MM-DD HH:MM:SS / YYYY-MM-DDTHH:MM:SS
# with optional fractional seconds and timezone suffixes (Z, +HHMM, +HH:MM).
TIMESTAMP_PATTERN = re.compile(r'(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)')
OFFSET_WITH_COLON_PATTERN = re.compile(r'(?P<hours>[+-]\d{2}):(?P<minutes>\d{2})$')
ACTION_PATTERN = re.compile(r'\b(entrada|salida)\b')


def parse_timestamp(timestamp: str) -> datetime | None:
    for fmt in (DATETIME_FORMAT, '%Y-%m-%dT%H:%M:%S'):
        try:
            parsed = datetime.strptime(timestamp, fmt)
            return parsed.replace(tzinfo=config.TZ)
        except ValueError:
            continue

    normalized = timestamp.replace(',', '.')
    if normalized.endswith('Z'):
        normalized = f'{normalized[:-1]}+00:00'
    normalized = OFFSET_WITH_COLON_PATTERN.sub(
        lambda match: f"{match.group('hours')}{match.group('minutes')}",
        normalized,
    )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=config.TZ)
    return parsed.astimezone(config.TZ)


def _to_fichaje_record(line: str) -> dict[str, str] | None:
    lowered = line.lower()
    actions = ACTION_PATTERN.findall(lowered)
    unique_actions = set(actions)
    if len(unique_actions) != 1:
        return None
    tipo = next(iter(unique_actions))

    match = TIMESTAMP_PATTERN.search(line)
    if not match:
        return None
    parsed = parse_timestamp(match.group('timestamp'))
    if parsed is None:
        return None
    return {tipo: parsed.strftime(DATETIME_FORMAT)}


def _normalize_records(data: list[object]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized_item: dict[str, str] = {}
        for tipo in ('entrada', 'salida'):
            timestamp = item.get(tipo)
            if not isinstance(timestamp, str):
                continue
            parsed = parse_timestamp(timestamp)
            if parsed is None:
                continue
            normalized_item[tipo] = parsed.strftime(DATETIME_FORMAT)
        if normalized_item:
            normalized.append(normalized_item)
    return normalized


def _parse_fichaje_text(raw_data: str) -> list[dict[str, str]]:
    text = raw_data.strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        return _normalize_records(data)

    records: list[dict[str, str]] = []
    for line in text.splitlines():
        record = _to_fichaje_record(line)
        if record is not None:
            records.append(record)
    return records


def read_fichaje_log() -> list[dict[str, str]]:
    lock = config.get_file_lock(config.FICHAJE_FILE)
    with lock:
        try:
            raw_data = config.FICHAJE_FILE.read_text(encoding='utf-8')
        except (FileNotFoundError, OSError):
            return []
        return _parse_fichaje_text(raw_data)


def es_fichaje_realizado_hoy(tipo: str) -> bool:
    today = datetime.now(config.TZ).date()
    for registro in read_fichaje_log():
        timestamp = registro.get(tipo)
        if not timestamp:
            continue
        parsed = parse_timestamp(timestamp)
        if parsed is None:
            continue
        if parsed.date() == today:
            return True
    return False


def get_today_fichajes() -> dict[str, str | None]:
    today = datetime.now(config.TZ).date()
    latest: dict[str, datetime | None] = {'entrada': None, 'salida': None}

    for registro in read_fichaje_log():
        for tipo in ('entrada', 'salida'):
            timestamp = registro.get(tipo)
            if not timestamp:
                continue
            parsed = parse_timestamp(timestamp)
            if parsed is None or parsed.date() != today:
                continue
            current = latest[tipo]
            if current is None or parsed > current:
                latest[tipo] = parsed

    return {
        'entrada': latest['entrada'].strftime(DATETIME_FORMAT) if latest['entrada'] else None,
        'salida': latest['salida'].strftime(DATETIME_FORMAT) if latest['salida'] else None,
    }


def get_fichaje_hoy(tipo: str) -> str | None:
    return get_today_fichajes().get(tipo)


def write_fichaje_log(tipo: str, timestamp: str) -> None:
    lock = config.get_file_lock(config.FICHAJE_FILE)
    with lock:
        try:
            raw_data = config.FICHAJE_FILE.read_text(encoding='utf-8')
        except (FileNotFoundError, OSError):
            raw_data = ''
        registros = _parse_fichaje_text(raw_data)
        registros.append({tipo: timestamp})
        config.ensure_parent(config.FICHAJE_FILE)
        with config.FICHAJE_FILE.open('w', encoding='utf-8') as handle:
            json.dump(registros, handle, indent=2, ensure_ascii=False)
