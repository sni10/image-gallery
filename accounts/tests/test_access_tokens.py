from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from ..authentication import BearerAccessTokenAuthentication
from ..services.access_tokens import AccessTokenService, InvalidAccessToken


def claims(user, **overrides):
    now = timezone.now()
    return {'sub': str(user.pk), 'type': 'access', 'iat': now, 'exp': now + timedelta(minutes=5), **overrides}


class AccessTokenTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')

    def get(self, token):
        return self.client.get('/galleries', HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_roundtrip(self):
        self.assertEqual(AccessTokenService().verify(AccessTokenService().issue(self.user)), self.user.pk)

    def test_authenticates_user(self):
        request = APIRequestFactory().get('/', HTTP_AUTHORIZATION=f'Bearer {AccessTokenService().issue(self.user)}')
        user, _ = BearerAccessTokenAuthentication().authenticate(request)
        self.assertEqual(user, self.user)

    def test_public_endpoint(self):
        self.assertEqual(self.client.get('/galleries').status_code, 200)  # no header -> anonymous
        self.assertEqual(self.get(AccessTokenService().issue(self.user)).status_code, 200)
        self.assertEqual(self.client.get('/galleries', HTTP_AUTHORIZATION='Basic abc').status_code, 200)

    def test_rejected_tokens(self):
        bad = {
            'garbage': 'not-a-jwt',
            'empty': '',
            'expired': AccessTokenService(lifetime=timedelta(seconds=-1)).issue(self.user),
            'forged': jwt.encode(claims(self.user), 'another-secret-key-of-sufficient-length!!', algorithm='HS256'),
            'alg none': jwt.encode(claims(self.user), None, algorithm='none'),
            'refresh type': jwt.encode(claims(self.user, type='refresh'), settings.SECRET_KEY, algorithm='HS256'),
            'no exp': jwt.encode({'sub': str(self.user.pk), 'type': 'access', 'iat': timezone.now()},
                                 settings.SECRET_KEY, algorithm='HS256'),
            'bad sub': jwt.encode(claims(self.user, sub='abc'), settings.SECRET_KEY, algorithm='HS256'),
        }
        for name, token in bad.items():
            with self.subTest(name):
                self.assertEqual(self.get(token).status_code, 401)
                if token:
                    with self.assertRaises(InvalidAccessToken):
                        AccessTokenService().verify(token)

    def test_inactive_or_deleted_user(self):
        token = AccessTokenService().issue(self.user)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.get(token).status_code, 401)
        self.user.delete()
        self.assertEqual(self.get(token).status_code, 401)
