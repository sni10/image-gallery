from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.utils.crypto import constant_time_compare, salted_hmac


class InvalidEmailToken(Exception):
    pass


class EmailTokenService:
    """One-time tokens for links in emails, without a DB table.

    The token is signed, expires after `max_age` and carries a fingerprint of the account state
    (active flag, password hash, email). Once that state changes - the account is activated,
    the email or password is changed - every token issued before becomes invalid.
    """

    salt = 'accounts.email-token'

    def __init__(self, max_age: timedelta = timedelta(hours=24)):
        self.max_age = max_age

    def make(self, user, purpose: str, **data) -> str:
        payload = {'uid': user.profile.public_id, 'purpose': purpose, 'state': self._state(user), **data}
        return signing.dumps(payload, salt=self.salt, compress=True)

    def read(self, token: str, purpose: str):
        """Return (user, payload) for a valid token of this purpose, raise InvalidEmailToken otherwise."""
        try:
            payload = signing.loads(token, salt=self.salt, max_age=self.max_age)
        except signing.BadSignature as exc:  # includes SignatureExpired
            raise InvalidEmailToken(str(exc)) from exc
        if payload.get('purpose') != purpose:
            raise InvalidEmailToken('wrong purpose')
        uid = payload.get('uid')
        user = get_user_model().objects.filter(profile__public_id=uid).first() if isinstance(uid, str) else None
        if user is None or not constant_time_compare(payload.get('state', ''), self._state(user)):
            raise InvalidEmailToken('already used or account changed')
        return user, payload

    def _state(self, user) -> str:
        return salted_hmac(self.salt, f'{user.is_active}|{user.password}|{user.email}').hexdigest()
