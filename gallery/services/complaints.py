import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage

from ..models import Complaint

logger = logging.getLogger(__name__)

SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def captcha_passed(token: str, ip: str) -> bool:
    """Checks a Cloudflare Turnstile token. Cloudflare down or a timeout counts as not passed."""
    data = urllib.parse.urlencode({'secret': settings.TURNSTILE_SECRET, 'response': token, 'remoteip': ip}).encode()
    try:
        with urllib.request.urlopen(SITEVERIFY_URL, data, timeout=5) as r:
            return json.load(r).get('success') is True
    except Exception:
        logger.warning('Turnstile siteverify failed', exc_info=True)
        return False


class ComplaintService:
    """Stores a complaint and emails it to COMPLAINTS_EMAIL (never shown to visitors), Reply-To = the sender."""

    def submit(self, *, email: str, photo_url: str, message: str, ip: str, user_agent: str, user=None) -> Complaint:
        complaint = Complaint.objects.create(email=email, photo_url=photo_url, message=message, ip=ip[:64],
                                             user_agent=user_agent[:500], user=user)
        if not settings.COMPLAINTS_EMAIL:
            logger.warning('COMPLAINTS_EMAIL is not set, complaint %s is only in the admin', complaint.pk)
            return complaint
        try:  # the complaint is saved; a mail failure must not become a 500 for the visitor
            self._message(complaint).send()
        except Exception:
            logger.exception('Could not email complaint %s', complaint.pk)
        return complaint

    @staticmethod
    def _message(c: Complaint) -> EmailMessage:
        user = f'{c.user.pk} ({c.user.email})' if c.user else 'гость'
        body = '\n'.join([
            f'Email: {c.email}',
            f'Фото: {c.photo_url or "—"}',
            f'Пользователь: {user}',
            f'IP: {c.ip}',
            f'User-Agent: {c.user_agent}',
            f'Время (UTC): {c.created_at:%Y-%m-%d %H:%M:%S}',
            '',
            c.message,
        ])
        return EmailMessage(f'Жалоба: {c.photo_url or "без ссылки"}', body, None, [settings.COMPLAINTS_EMAIL],
                            reply_to=[c.email])  # None -> DEFAULT_FROM_EMAIL
