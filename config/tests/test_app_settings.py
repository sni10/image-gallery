import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from ..app_settings import load_settings

VALID_ENV = {
    'DJANGO_SECRET_KEY': 'k' * 50,
    'DJANGO_ALLOWED_HOSTS': 'a.com, b.com',
    'DB_NAME': 'gallery',
    'DB_USER': 'u',
    'DB_PASSWORD': 'p',
    'CORS_ALLOWED_ORIGINS': 'https://a.com,http://localhost:5173',
}


class LoadSettingsTest(SimpleTestCase):
    def load(self, env_file=None, **overrides):
        env = {k: v for k, v in {**VALID_ENV, **overrides}.items() if v is not None}
        with mock.patch.dict(os.environ, env, clear=True):
            return load_settings(env_file)

    def assertInvalid(self, *expected_vars, **overrides):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            self.load(**overrides)
        for var in expected_vars:
            self.assertIn(var, str(ctx.exception))

    def test_valid_env_with_defaults(self):
        s = self.load()
        self.assertFalse(s.django.debug)
        self.assertEqual(s.django.allowed_hosts, ['a.com', 'b.com'])
        self.assertEqual(s.cors.allowed_origins, ['https://a.com', 'http://localhost:5173'])
        self.assertEqual((s.db.host, s.db.port), ('db', 5432))

    def test_reports_all_errors_at_once(self):
        self.assertInvalid('DB_PORT', 'EMAIL_PORT', 'DB_PASSWORD', DB_PORT='99999', EMAIL_PORT='abc', DB_PASSWORD=None)

    def test_production_requires_strong_key_and_hosts(self):
        self.assertInvalid('DJANGO_SECRET_KEY', DJANGO_SECRET_KEY='short')
        self.assertInvalid('DJANGO_ALLOWED_HOSTS', DJANGO_ALLOWED_HOSTS='')
        self.assertTrue(self.load(DJANGO_DEBUG='true', DJANGO_SECRET_KEY='short', DJANGO_ALLOWED_HOSTS='').django.debug)

    def test_cors_origin_with_path_rejected(self):
        self.assertInvalid('CORS_ALLOWED_ORIGINS', CORS_ALLOWED_ORIGINS='https://a.com/app')

    def test_email_and_frontend(self):
        s = self.load()
        self.assertEqual((s.email.backend, s.frontend.url), ('console', 'http://localhost:5173'))
        s = self.load(EMAIL_BACKEND='smtp', EMAIL_HOST='smtp.example.com', EMAIL_PORT='465', EMAIL_PASSWORD='p',
                      FRONTEND_URL='https://gallery.example.com')
        self.assertEqual((s.email.host, s.email.port, s.frontend.url),
                         ('smtp.example.com', 465, 'https://gallery.example.com'))
        self.assertNotIn('p', repr(s.email.password))  # secret is not printed

    def test_email_and_frontend_invalid(self):
        self.assertInvalid('EMAIL_PORT', 'EMAIL_BACKEND', 'FRONTEND_URL',
                           EMAIL_PORT='0', EMAIL_BACKEND='sendmail', FRONTEND_URL='https://a.com/app')

    def test_reads_env_file_and_env_vars_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / '.env'
            env_file.write_text('DB_HOST=db.internal\nDB_PORT=6543\n', encoding='utf-8')
            s = self.load(env_file, DB_PORT='7000')
        self.assertEqual((s.db.host, s.db.port), ('db.internal', 7000))
