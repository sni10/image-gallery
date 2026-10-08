from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from ..services.email_tokens import EmailTokenService, InvalidEmailToken


class EmailTokenServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x', is_active=False)
        self.tokens = EmailTokenService()

    def assertInvalid(self, token, purpose='confirm', tokens=None):
        with self.assertRaises(InvalidEmailToken):
            (tokens or self.tokens).read(token, purpose)

    def test_valid_token_carries_data(self):
        token = self.tokens.make(self.user, 'change', new_email='new@example.com')
        user, payload = self.tokens.read(token, 'change')
        self.assertEqual((user, payload['new_email']), (self.user, 'new@example.com'))

    def test_dies_after_activation(self):
        token = self.tokens.make(self.user, 'confirm')
        self.tokens.read(token, 'confirm')
        self.user.is_active = True
        self.user.save()
        self.assertInvalid(token)

    def test_dies_after_email_or_password_change(self):
        for change in (lambda u: setattr(u, 'email', 'other@example.com'), lambda u: u.set_password('new')):
            token = self.tokens.make(self.user, 'confirm')
            change(self.user)
            self.user.save()
            self.assertInvalid(token)

    def test_expired_tampered_wrong_purpose_deleted_user(self):
        token = self.tokens.make(self.user, 'confirm')
        self.assertInvalid(token, tokens=EmailTokenService(max_age=timedelta(seconds=-1)))
        self.assertInvalid(token[:-2] + ('AA' if not token.endswith('AA') else 'BB'))
        self.assertInvalid(token, purpose='change')
        self.assertInvalid('garbage')
        self.user.delete()
        self.assertInvalid(token)
