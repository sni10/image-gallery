from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

ALGORITHM = 'HS256'


class InvalidAccessToken(Exception):
    pass


class AccessTokenService:
    """Short-lived stateless access tokens: JWT HS256 signed with SECRET_KEY, never stored."""

    def __init__(self, lifetime: timedelta = timedelta(minutes=15)):
        self.lifetime = lifetime

    def issue(self, user) -> str:
        now = timezone.now()
        claims = {'sub': str(user.pk), 'type': 'access', 'iat': now, 'exp': now + self.lifetime}
        return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)

    def verify(self, token: str) -> int:
        """Return the user id from a valid access token, raise InvalidAccessToken otherwise."""
        try:
            claims = jwt.decode(
                token, settings.SECRET_KEY,
                algorithms=[ALGORITHM],  # pinned: rejects "none" and algorithm confusion
                options={'require': ['sub', 'type', 'iat', 'exp']},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidAccessToken(str(exc)) from exc
        if claims['type'] != 'access' or not claims['sub'].isdigit():
            raise InvalidAccessToken('not an access token')
        return int(claims['sub'])
