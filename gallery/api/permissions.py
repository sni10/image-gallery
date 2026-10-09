import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasIngestKey(BasePermission):
    """`X-Api-Key` equals INGEST_API_KEY. Not `Authorization: Bearer`: that header belongs to user JWTs.
    No key configured -> everyone is refused."""

    message = 'Missing or invalid X-Api-Key.'

    def has_permission(self, request, view):
        key = settings.INGEST_API_KEY
        given = request.headers.get('X-Api-Key', '')
        return bool(key) and hmac.compare_digest(given.encode(), key.encode())
