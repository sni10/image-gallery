from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail


class AccountEmails:
    """Plain-text account emails (English). Links point to the SPA (FRONTEND_URL), which posts the token to the API."""

    def send_confirmation(self, user, token: str) -> None:
        self._send(
            user.email, 'Confirm your email',
            'Thanks for signing up for ArtAI. To activate your account, open this link '
            f'(valid for 24 hours):\n\n{self._link("confirm-email", token)}\n\n'
            "If you didn't sign up, just ignore this email.",
        )

    def send_email_change(self, new_email: str, token: str) -> None:
        self._send(
            new_email, 'Confirm your new email',
            'To make this the email address of your ArtAI account, open this link '
            f'(valid for 24 hours):\n\n{self._link("confirm-email-change", token)}\n\n'
            "If you didn't request this, just ignore this email.",
        )

    def send_email_changed_notice(self, old_email: str, new_email: str) -> None:
        self._send(
            old_email, 'Your account email was changed',
            f'The email address of your ArtAI account was changed to {new_email}. '
            "If you didn't do this, contact support right away.",
        )

    def send_password_reset(self, user, token: str) -> None:
        self._send(
            user.email, 'Reset your password',
            'To set a new password for your ArtAI account, open this link '
            f'(valid for 1 hour):\n\n{self._link("reset-password", token)}\n\n'
            "If you didn't request a password reset, just ignore this email.",
        )

    @staticmethod
    def _link(path: str, token: str) -> str:
        return f'{settings.FRONTEND_URL}/{path}?token={quote(token, safe="")}'

    @staticmethod
    def _send(to: str, subject: str, body: str) -> None:
        send_mail(subject, body, None, [to])  # None -> DEFAULT_FROM_EMAIL
