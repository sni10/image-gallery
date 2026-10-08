from django.contrib.auth import get_user_model
from django.utils import timezone

from .registration import normalize_email
from .token_pairs import TokenPair, TokenPairService


class InvalidCredentials(Exception):
    pass


class EmailNotConfirmed(Exception):
    pass


class AuthService:
    """Login by email + password, token refresh and logout."""

    def __init__(self, token_pairs: TokenPairService | None = None):
        self._token_pairs = token_pairs or TokenPairService()

    def login(self, email: str, password: str) -> TokenPair:
        User = get_user_model()
        user = User.objects.filter(username=normalize_email(email)).first()
        if user is None:
            User().set_password(password)  # same hashing cost as a real check: no timing hint that the email is unknown
            raise InvalidCredentials
        if not user.check_password(password):
            raise InvalidCredentials
        if not user.is_active:
            raise EmailNotConfirmed  # only reachable with the right password
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        return self._token_pairs.issue(user)

    def refresh(self, raw_refresh: str) -> TokenPair:
        return self._token_pairs.rotate(raw_refresh)

    def logout(self, raw_refresh: str) -> None:
        self._token_pairs.revoke(raw_refresh)
