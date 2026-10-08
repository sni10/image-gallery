import re
from urllib.parse import unquote

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from ..services.email_tokens import InvalidEmailToken
from ..services.registration import RegistrationService

STRONG = 'correct-horse-battery'


def link_token(message, path='confirm-email'):
    match = re.search(rf'https://gallery\.test/{path}\?token=(\S+)', message.body)
    return unquote(match.group(1))


@override_settings(FRONTEND_URL='https://gallery.test')
class RegistrationServiceTest(TestCase):
    def setUp(self):
        self.service = RegistrationService()

    def test_register_creates_inactive_account_and_sends_link(self):
        user = self.service.register(' Anna@Example.com ', STRONG)
        self.assertEqual((user.username, user.email, user.is_active), ('anna@example.com', 'anna@example.com', False))
        self.assertTrue(user.check_password(STRONG))
        self.assertNotEqual(user.password, STRONG)  # only a hash is stored
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['anna@example.com'])
        self.assertTrue(link_token(mail.outbox[0]))

    def test_confirmed_email_taken(self):
        User.objects.create_user('anna@example.com', 'anna@example.com', STRONG)
        with self.assertRaises(ValidationError) as ctx:
            self.service.register('anna@example.com', STRONG)
        self.assertIn('email', ctx.exception.message_dict)
        self.assertEqual(mail.outbox, [])

    def test_reregister_unconfirmed_replaces_password_and_kills_old_link(self):
        self.service.register('anna@example.com', STRONG)
        old_token = link_token(mail.outbox[0])
        self.service.register('anna@example.com', 'another-strong-passphrase')
        user = User.objects.get()
        self.assertTrue(user.check_password('another-strong-passphrase'))
        self.assertEqual(len(mail.outbox), 2)
        with self.assertRaises(InvalidEmailToken):
            self.service.confirm(old_token)
        self.service.confirm(link_token(mail.outbox[1]))

    def test_invalid_email_or_weak_password(self):
        for email, password, field in (('no-at-sign', STRONG, 'email'), ('anna@example.com', '12345678', 'password'),
                                       ('anna@example.com', 'anna@example.com', 'password')):
            with self.subTest(email=email, password=password):
                with self.assertRaises(ValidationError) as ctx:
                    self.service.register(email, password)
                self.assertIn(field, ctx.exception.message_dict)
        self.assertFalse(User.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_confirm_activates_and_returns_tokens(self):
        self.service.register('anna@example.com', STRONG)
        pair = self.service.confirm(link_token(mail.outbox[0]))
        self.assertTrue(User.objects.get().is_active)
        self.assertTrue(pair.access and pair.refresh)

    def test_resend_only_for_unconfirmed(self):
        self.service.register('anna@example.com', STRONG)
        User.objects.create_user('bob@example.com', 'bob@example.com', STRONG)
        mail.outbox.clear()
        for email in ('ANNA@example.com', 'bob@example.com', 'nobody@example.com'):
            self.service.resend_confirmation(email)
        self.assertEqual([m.to for m in mail.outbox], [['anna@example.com']])
