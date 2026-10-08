from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from .email_tokens import EmailTokenService
from .emails import AccountEmails
from .token_pairs import TokenPair, TokenPairService

CONFIRM = 'confirm'


def normalize_email(email: str) -> str:
    return email.strip().lower()


class RegistrationService:
    """Sign-up with email confirmation. The email (lowercased) is also the username."""

    def __init__(self, tokens: EmailTokenService | None = None, emails: AccountEmails | None = None,
                 token_pairs: TokenPairService | None = None):
        self._tokens = tokens or EmailTokenService()
        self._emails = emails or AccountEmails()
        self._token_pairs = token_pairs or TokenPairService()

    @transaction.atomic
    def register(self, email: str, password: str):
        """Create an inactive account and email a confirmation link. Re-registering an unconfirmed
        email replaces its password (old links die) and sends a new link. Raises ValidationError."""
        email = normalize_email(email)
        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValidationError({'email': exc.messages})
        User = get_user_model()
        user = User.objects.select_for_update().filter(username=email).first()
        if user is not None and user.is_active:
            raise ValidationError({'email': ['Этот email уже зарегистрирован.']})
        user = user or User(username=email, email=email, is_active=False)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise ValidationError({'password': exc.messages})
        user.set_password(password)
        user.save()
        self._emails.send_confirmation(user, self._tokens.make(user, CONFIRM))  # failure rolls the account back
        return user

    def confirm(self, token: str) -> TokenPair:
        """Activate the account from the emailed token and log the user in. Raises InvalidEmailToken."""
        user, _ = self._tokens.read(token, CONFIRM)
        user.is_active = True
        user.save(update_fields=['is_active'])
        return self._token_pairs.issue(user)

    def resend_confirmation(self, email: str) -> None:
        """Send a new link only if an unconfirmed account exists; callers must not reveal which case it was."""
        user = get_user_model().objects.filter(username=normalize_email(email), is_active=False).first()
        if user is not None:
            self._emails.send_confirmation(user, self._tokens.make(user, CONFIRM))
