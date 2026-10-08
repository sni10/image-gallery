from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail


class AccountEmails:
    """Plain-text account emails. Links point to the SPA (FRONTEND_URL), which posts the token to the API."""

    def send_confirmation(self, user, token: str) -> None:
        self._send(
            user.email, 'Подтвердите email',
            'Вы зарегистрировались в галерее. Чтобы активировать аккаунт, откройте ссылку '
            f'(действует 24 часа):\n\n{self._link("confirm-email", token)}\n\n'
            'Если это были не вы, просто проигнорируйте письмо.',
        )

    def send_email_change(self, new_email: str, token: str) -> None:
        self._send(
            new_email, 'Подтвердите новый email',
            'Чтобы сделать этот адрес email вашего аккаунта в галерее, откройте ссылку '
            f'(действует 24 часа):\n\n{self._link("confirm-email-change", token)}\n\n'
            'Если это были не вы, просто проигнорируйте письмо.',
        )

    def send_email_changed_notice(self, old_email: str, new_email: str) -> None:
        self._send(
            old_email, 'Email аккаунта изменён',
            f'Email вашего аккаунта в галерее изменён на {new_email}. '
            'Если это были не вы, срочно обратитесь в поддержку.',
        )

    @staticmethod
    def _link(path: str, token: str) -> str:
        return f'{settings.FRONTEND_URL}/{path}?token={quote(token, safe="")}'

    @staticmethod
    def _send(to: str, subject: str, body: str) -> None:
        send_mail(subject, body, None, [to])  # None -> DEFAULT_FROM_EMAIL
