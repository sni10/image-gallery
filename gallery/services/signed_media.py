"""Expiring signatures for links to originals: `?exp=<unix>&sig=<hmac>`, checked by media_auth (Caddy forward_auth).

`exp` is rounded up to the hour, so one photo keeps the same link for an hour and browsers can cache it.
The key is MEDIA_SIGNING_KEY, not SECRET_KEY: rotating it invalidates links, not sessions.
"""
import hashlib
import hmac
import math
import time

from django.conf import settings

HOUR = 3600


def signed_query(path: str, now: float | None = None) -> str:
    """Query string granting access to `path` (URL path, as the web server sees it) for MEDIA_URL_TTL..+1h."""
    exp = math.ceil(((time.time() if now is None else now) + settings.MEDIA_URL_TTL) / HOUR) * HOUR
    return f'exp={exp}&sig={_sig(path, exp)}'


def is_valid(path: str, exp: str | None, sig: str | None, now: float | None = None) -> bool:
    try:
        exp_at = int(exp)
    except (TypeError, ValueError):
        return False
    alive = exp_at > (time.time() if now is None else now)
    return alive and hmac.compare_digest(_sig(path, exp_at), sig or '')


def _sig(path: str, exp: int) -> str:
    return hmac.new(settings.MEDIA_SIGNING_KEY.encode(), f'{path}\n{exp}'.encode(), hashlib.sha256).hexdigest()
