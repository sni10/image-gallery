from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from .test_registration import STRONG, link_token


@override_settings(FRONTEND_URL='https://gallery.test')
class ApiTestCase(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache and would leak between tests

    def post(self, url, ip='10.0.0.1', **data):
        return self.client.post(url, data, content_type='application/json', HTTP_X_FORWARDED_FOR=ip)


class RegistrationApiTest(ApiTestCase):
    def test_register(self):
        r = self.post('/auth/register', email=' Anna@Example.com ', password=STRONG)
        self.assertEqual((r.status_code, r.json()), (201, {'email': 'anna@example.com'}))
        self.assertFalse(User.objects.get().is_active)
        self.assertEqual(mail.outbox[0].to, ['anna@example.com'])

    def test_register_errors(self):
        User.objects.create_user('taken@example.com', 'taken@example.com', STRONG)
        cases = [
            ({'email': 'taken@example.com', 'password': STRONG}, 'email'),
            ({'email': 'no-at-sign', 'password': STRONG}, 'email'),
            ({'email': 'anna@example.com', 'password': '12345678'}, 'password'),
            ({'email': 'anna@example.com'}, 'password'),
        ]
        for data, field in cases:
            with self.subTest(data=data):
                r = self.post('/auth/register', **data)
                self.assertEqual(r.status_code, 400)
                self.assertIn(field, r.json())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(mail.outbox, [])

    def test_confirm_email(self):
        self.post('/auth/register', email='anna@example.com', password=STRONG)
        token = link_token(mail.outbox[0])
        r = self.post('/auth/confirm-email', token=token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {'access', 'refresh'})
        self.assertTrue(User.objects.get().is_active)
        access = r.json()['access']
        self.assertEqual(self.client.get('/galleries', HTTP_AUTHORIZATION=f'Bearer {access}').status_code, 200)

        reused = self.post('/auth/confirm-email', token=token)
        self.assertEqual((reused.status_code, list(reused.json())), (400, ['token']))

    def test_confirm_bad_tokens(self):
        for token in ('forged', ''):
            with self.subTest(token=token):
                self.assertEqual(self.post('/auth/confirm-email', token=token).status_code, 400)

    def test_resend_always_204(self):
        self.post('/auth/register', email='anna@example.com', password=STRONG)
        User.objects.create_user('bob@example.com', 'bob@example.com', STRONG)
        mail.outbox.clear()
        for email in ('anna@example.com', 'bob@example.com', 'nobody@example.com', 'not-an-email'):
            with self.subTest(email=email):
                r = self.post('/auth/resend-confirmation', email=email)
                self.assertEqual((r.status_code, r.content), (204, b''))
        self.assertEqual([m.to for m in mail.outbox], [['anna@example.com']])


class LoginApiTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        User.objects.create_user('anna@example.com', 'anna@example.com', STRONG)
        User.objects.create_user('new@example.com', 'new@example.com', STRONG, is_active=False)

    def login(self, email='anna@example.com', password=STRONG):
        return self.post('/auth/login', email=email, password=password)

    def test_login(self):
        r = self.login(email=' ANNA@example.com ')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {'access', 'refresh'})
        self.assertIsNotNone(User.objects.get(username='anna@example.com').last_login)

    def test_wrong_email_or_password_same_401(self):
        wrong_password, unknown_email = self.login(password='nope-nope-nope'), self.login(email='x@example.com')
        self.assertEqual((wrong_password.status_code, unknown_email.status_code), (401, 401))
        self.assertEqual(wrong_password.json(), unknown_email.json())

    def test_unconfirmed(self):
        r = self.login(email='new@example.com')
        self.assertEqual((r.status_code, r.json()['code']), (403, 'email_not_confirmed'))
        self.assertNotIn('access', r.json())
        self.assertEqual(self.login(email='new@example.com', password='wrong-password').status_code, 401)

    def test_refresh_rotation_and_reuse(self):
        first = self.login().json()
        second = self.post('/auth/refresh', refresh=first['refresh'])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(set(second.json()), {'access', 'refresh'})
        self.assertEqual(self.post('/auth/refresh', refresh=first['refresh']).status_code, 401)  # reuse
        self.assertEqual(self.post('/auth/refresh', refresh=second.json()['refresh']).status_code, 401)  # all revoked
        self.assertEqual(self.post('/auth/refresh', refresh='made-up').status_code, 401)

    def test_logout(self):
        session, other = self.login().json(), self.login().json()
        r = self.post('/auth/logout', refresh=session['refresh'])
        self.assertEqual((r.status_code, r.content), (204, b''))
        self.assertEqual(self.post('/auth/refresh', refresh=session['refresh']).status_code, 401)
        self.assertEqual(self.post('/auth/refresh', refresh=other['refresh']).status_code, 200)


class ThrottlingTest(ApiTestCase):
    def test_eleventh_request_per_minute_is_429(self):
        endpoints = {
            '/auth/login': {'email': 'a@example.com', 'password': 'x'},
            '/auth/register': {'email': 'bad', 'password': 'x'},
            '/auth/resend-confirmation': {'email': 'a@example.com'},
            '/auth/confirm-email': {'token': 'bad'},
        }
        for url, data in endpoints.items():
            with self.subTest(url=url):
                codes = [self.post(url, **data).status_code for _ in range(11)]
                self.assertNotIn(429, codes[:10])
                self.assertEqual(codes[10], 429)

    def test_limit_is_per_client_ip(self):
        for _ in range(10):
            self.post('/auth/login', email='a@example.com', password='x')
        self.assertEqual(self.post('/auth/login', email='a@example.com', password='x').status_code, 429)
        self.assertEqual(self.post('/auth/login', ip='10.0.0.2', email='a@example.com', password='x').status_code, 401)
        spoofed = self.post('/auth/login', ip='1.2.3.4, 10.0.0.1', email='a@example.com', password='x')
        self.assertEqual(spoofed.status_code, 429)  # a forged first X-Forwarded-For entry doesn't reset the limit
