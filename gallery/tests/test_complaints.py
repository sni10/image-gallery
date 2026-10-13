from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.services.access_tokens import AccessTokenService

from ..models import Complaint

VALID = {'email': 'anna@example.com', 'photoUrl': 'https://artai.win/photos/abc123', 'message': 'Это моё лицо, удалите.'}


@override_settings(COMPLAINTS_EMAIL='admin@example.com')
class ComplaintApiTest(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters

    def post(self, ip='10.0.0.1', **data):
        return self.client.post('/complaints', data, content_type='application/json', HTTP_X_FORWARDED_FOR=ip,
                                HTTP_USER_AGENT='TestBrowser/1.0', **self.headers)

    headers = {}

    def test_valid_complaint_is_stored_and_emailed(self):
        r = self.post(**VALID)
        self.assertEqual((r.status_code, r.content), (204, b''))
        c = Complaint.objects.get()
        self.assertEqual((c.email, c.photo_url, c.ip, c.user_agent, c.user, c.handled),
                         ('anna@example.com', VALID['photoUrl'], '10.0.0.1', 'TestBrowser/1.0', None, False))
        [m] = mail.outbox
        self.assertEqual((m.to, m.reply_to), (['admin@example.com'], ['anna@example.com']))
        self.assertEqual(m.subject, f'Жалоба: {VALID["photoUrl"]}')
        for part in (VALID['message'], '10.0.0.1', 'TestBrowser/1.0', 'гость'):
            self.assertIn(part, m.body)

    def test_with_token_links_user(self):
        user = User.objects.create_user('bob@example.com', 'bob@example.com', 'x')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(user)}'}
        self.assertEqual(self.post(**VALID).status_code, 204)
        self.assertEqual(Complaint.objects.get().user, user)
        self.assertIn('bob@example.com', mail.outbox[0].body)

    def test_field_errors(self):
        cases = [
            ({'email': None}, 'email'),
            ({'email': 'not-an-email'}, 'email'),
            ({'message': '   short   '}, 'message'),  # 5 chars after strip
            ({'message': 'x' * 5001}, 'message'),
            ({'photoUrl': 'not a url'}, 'photoUrl'),
        ]
        for change, field in cases:
            with self.subTest(change=change):
                data = {k: v for k, v in {**VALID, **change}.items() if v is not None}
                r = self.post(**data)
                self.assertEqual(r.status_code, 400)
                self.assertIn(field, r.json())
        self.assertFalse(Complaint.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_photo_url_optional(self):
        self.assertEqual(self.post(email='a@example.com', message='x' * 10, photoUrl='').status_code, 204)
        self.assertEqual(self.post(email='a@example.com', message='x' * 10).status_code, 204)
        self.assertEqual(mail.outbox[0].subject, 'Жалоба: без ссылки')

    def test_sixth_per_hour_from_one_ip_is_429(self):
        codes = [self.post(**VALID).status_code for _ in range(6)]
        self.assertEqual(codes, [204] * 5 + [429])
        self.assertEqual(self.post(ip='10.0.0.2', **VALID).status_code, 204)

    def test_mail_failure_still_204_and_stored(self):
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError('smtp down')), \
                self.assertLogs('gallery.services.complaints', 'ERROR'):
            r = self.post(**VALID)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Complaint.objects.count(), 1)

    @override_settings(COMPLAINTS_EMAIL='')
    def test_no_address_configured_only_stores(self):
        with self.assertLogs('gallery.services.complaints', 'WARNING'):
            self.assertEqual(self.post(**VALID).status_code, 204)
        self.assertEqual((Complaint.objects.count(), mail.outbox), (1, []))
