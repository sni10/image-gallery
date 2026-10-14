from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .email_tokens import EmailTokenService
from .emails import AccountEmails
from .registration import normalize_email
from .token_pairs import TokenPair, TokenPairService

RESET_PASSWORD = 'reset-password'


class PasswordResetService:
    """Forgotten password: an emailed link with a one-time token (it carries the password hash fingerprint,
    so it dies once any new password is set) that sets a new password and logs the user in."""

    def __init__(self, tokens: EmailTokenService | None = None, emails: AccountEmails | None = None,
                 token_pairs: TokenPairService | None = None):
        self._tokens = tokens or EmailTokenService(max_age=settings.PASSWORD_RESET_TTL)
        self._emails = emails or AccountEmails()
        self._token_pairs = token_pairs or TokenPairService()

    def request(self, email: str) -> None:
        """Email a link if the account exists (confirmed or not); callers must not reveal which case it was."""
        user = get_user_model().objects.filter(username=normalize_email(email)).first()
        if user is not None:
            self._emails.send_password_reset(user, self._tokens.make(user, RESET_PASSWORD))

    @transaction.atomic
    def confirm(self, token: str, password: str) -> TokenPair:
        """Set the new password, confirm the email (the link proves the mailbox), revoke all refresh tokens and
        log in. Raises InvalidEmailToken, or ValidationError({'password'}) leaving the token valid."""
        user, _ = self._tokens.read(token, RESET_PASSWORD)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise ValidationError({'password': exc.messages})
        user.set_password(password)
        user.is_active = True
        user.save(update_fields=['password', 'is_active'])
        self._token_pairs.revoke_all(user)
        return self._token_pairs.issue(user)
