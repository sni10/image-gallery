import base64
from datetime import UTC, datetime

from django.utils.crypto import salted_hmac


def make_public_id(label: str, pk: int, link_date: datetime) -> str:
    """Opaque public id: 26 chars [a-z2-7] = 128 bits of HMAC-SHA256(SECRET_KEY) over model, pk and link date.

    Reveals neither the pk nor the number or order of records; changes when link_date changes.
    """
    message = f'{label}:{pk}:{link_date.astimezone(UTC).isoformat(timespec="microseconds")}'
    digest = salted_hmac('public-id', message, algorithm='sha256').digest()
    return base64.b32encode(digest[:16]).decode().lower().rstrip('=')
