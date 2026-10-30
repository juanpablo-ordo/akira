"""User-selected time zone for chat and display; MT5 timestamps remain UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "America/Guatemala"


def selected_timezone(cfg):
    return str((cfg.get("locale") or {}).get("timezone") or DEFAULT_TIMEZONE).strip()


def user_timezone(cfg):
    name = selected_timezone(cfg)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, OSError):
        # Windows without tzdata may not contain the IANA database. The
        # Guatemala fallback is exact year-round; all others use UTC until
        # the time-zone database is repaired, never the computer's guess.
        if name == DEFAULT_TIMEZONE:
            return timezone(timedelta(hours=-6), name=DEFAULT_TIMEZONE)
        return timezone.utc


def local_now(cfg):
    return datetime.now(timezone.utc).astimezone(user_timezone(cfg))


def format_local(utc_datetime, cfg):
    name = selected_timezone(cfg)
    return utc_datetime.astimezone(user_timezone(cfg)).strftime("%a %d %b %H:%M ") + name


def validate_timezone(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Selecciona una zona horaria IANA, por ejemplo America/Guatemala")
    if len(name) > 120:
        raise ValueError("Zona horaria demasiado larga")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, OSError):
        if name != DEFAULT_TIMEZONE:
            raise ValueError("Zona horaria desconocida: " + name) from None
    return name
