import re
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

ALGORITHM = 'HS256'
PUBLIC_ID = re.compile(r'[a-z2-7]{26}')


class InvalidAccessToken(Exception):
    pass


class AccessTokenService:
    """Short-lived stateless access tokens: JWT HS256 signed with SECRET_KEY, never stored."""

    def __init__(self, lifetime: timedelta = timedelta(minutes=15)):
        self.lifetime = lifetime

    def issue(self, user) -> str:
        now = timezone.now()
        claims = {'sub': user.profile.public_id, 'type': 'access', 'iat': now, 'exp': now + self.lifetime}
        return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)

    def verify(self, token: str) -> str:
        """Return the user's public id from a valid access token, raise InvalidAccessToken otherwise."""
        try:
            claims = jwt.decode(
                token, settings.SECRET_KEY,
                algorithms=[ALGORITHM],  # pinned: rejects "none" and algorithm confusion
                options={'require': ['sub', 'type', 'iat', 'exp']},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidAccessToken(str(exc)) from exc
        if claims['type'] != 'access' or not PUBLIC_ID.fullmatch(claims['sub']):
            raise InvalidAccessToken('not an access token')
        return claims['sub']
