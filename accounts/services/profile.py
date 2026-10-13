from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from .email_tokens import EmailTokenService
from .emails import AccountEmails
from .registration import normalize_email
from .token_pairs import TokenPair, TokenPairService

CHANGE_EMAIL = 'change-email'


class ProfileService:
    """Changes of the logged-in user's own account. Raise ValidationError keyed by argument name."""

    def __init__(self, tokens: EmailTokenService | None = None, emails: AccountEmails | None = None,
                 token_pairs: TokenPairService | None = None):
        self._tokens = tokens or EmailTokenService()
        self._emails = emails or AccountEmails()
        self._token_pairs = token_pairs or TokenPairService()

    def request_email_change(self, user, new_email: str, password: str) -> None:
        """Email a confirmation link to the new address; the current email stays until it is confirmed."""
        if not user.check_password(password):
            raise ValidationError({'password': ['Incorrect password.']})
        new_email = normalize_email(new_email)
        try:
            validate_email(new_email)
        except ValidationError as exc:
            raise ValidationError({'new_email': exc.messages})
        if new_email == user.email:
            raise ValidationError({'new_email': ['This is already your email.']})
        if _email_taken(new_email, user):
            raise ValidationError({'new_email': ['This email is already registered.']})
        self._emails.send_email_change(new_email, self._tokens.make(user, CHANGE_EMAIL, new_email=new_email))

    @transaction.atomic
    def confirm_email_change(self, token: str) -> str:
        """Apply the emailed change, notify the old address. Raises InvalidEmailToken or ValidationError."""
        user, payload = self._tokens.read(token, CHANGE_EMAIL)
        new_email = payload['new_email']
        if _email_taken(new_email, user):
            raise ValidationError({'token': ['This email is already registered to another account.']})
        old_email = user.email
        user.email = user.username = new_email  # the email is the login
        user.save(update_fields=['email', 'username'])
        self._emails.send_email_changed_notice(old_email, new_email)
        return new_email

    @transaction.atomic
    def change_password(self, user, current_password: str, new_password: str) -> TokenPair:
        """Set a new password and log out every other session: all refresh tokens are revoked."""
        if not user.check_password(current_password):
            raise ValidationError({'current_password': ['Incorrect password.']})
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            raise ValidationError({'new_password': exc.messages})
        user.set_password(new_password)
        user.save(update_fields=['password'])
        self._token_pairs.revoke_all(user)
        return self._token_pairs.issue(user)


    def delete_account(self, user, password: str) -> None:
        """Delete the user with profile, refresh tokens and favorites (cascade); complaints stay, unlinked.
        Raises AdminAccountProtected for staff (don't lock the site out) or ValidationError."""
        if user.is_staff or user.is_superuser:
            raise AdminAccountProtected
        if not user.check_password(password):
            raise ValidationError({'password': ['Wrong password.']})
        user.delete()


class AdminAccountProtected(Exception):
    pass


def _email_taken(email: str, user) -> bool:
    return get_user_model().objects.filter(username=email).exclude(pk=user.pk).exists()
