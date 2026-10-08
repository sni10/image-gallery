import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import RefreshToken
from .access_tokens import AccessTokenService


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str


class InvalidRefreshToken(Exception):
    pass


class TokenPairService:
    """Issues access+refresh pairs; rotates, revokes and detects reuse of refresh tokens."""

    def __init__(self, access_tokens: AccessTokenService | None = None, refresh_lifetime=timedelta(days=7)):
        self._access = access_tokens or AccessTokenService()
        self._refresh_lifetime = refresh_lifetime

    def issue(self, user) -> TokenPair:
        """New login session (login, email confirmation, password change)."""
        RefreshToken.objects.filter(user=user, expires_at__lte=timezone.now()).delete()  # housekeeping
        return self._issue(user, family=uuid.uuid4())

    def rotate(self, raw_refresh: str) -> TokenPair:
        """Exchange a refresh token for a new pair. Replaying an already exchanged token revokes every token
        of its user: either the owner or a thief holds a copy, so both get logged out. A token revoked by
        logout is simply rejected."""
        with transaction.atomic():
            token = (
                RefreshToken.objects.select_for_update().select_related('user')
                .filter(token_hash=_hash(raw_refresh)).first()
            )
            if token is None or token.expires_at <= timezone.now() or not token.user.is_active:
                raise InvalidRefreshToken('unknown or expired refresh token')
            if token.revoked_at is None:
                token.revoked_at, token.rotated = timezone.now(), True
                token.save(update_fields=['revoked_at', 'rotated'])
                return self._issue(token.user, family=token.family)
        if token.rotated:
            self.revoke_all(token.user)  # reuse detected; outside the block so the revocation is committed
        raise InvalidRefreshToken('refresh token revoked')

    def revoke(self, raw_refresh: str) -> None:
        RefreshToken.objects.filter(token_hash=_hash(raw_refresh), revoked_at=None).update(revoked_at=timezone.now())

    def revoke_all(self, user) -> None:
        RefreshToken.objects.filter(user=user, revoked_at=None).update(revoked_at=timezone.now())

    def _issue(self, user, family) -> TokenPair:
        raw = secrets.token_urlsafe(32)
        RefreshToken.objects.create(
            user=user, token_hash=_hash(raw), family=family, expires_at=timezone.now() + self._refresh_lifetime,
        )
        return TokenPair(access=self._access.issue(user), refresh=raw)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
