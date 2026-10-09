from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from ..authentication import BearerAccessTokenAuthentication
from ..services.access_tokens import AccessTokenService, InvalidAccessToken
from ..services.email_tokens import EmailTokenService, InvalidEmailToken


def claims(user, **overrides):
    now = timezone.now()
    return {'sub': user.profile.public_id, 'type': 'access', 'iat': now, 'exp': now + timedelta(minutes=5), **overrides}


class AccessTokenTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')

    def get(self, token):
        return self.client.get('/galleries', HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_roundtrip(self):
        self.assertEqual(AccessTokenService().verify(AccessTokenService().issue(self.user)), self.user.profile.public_id)

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
            'no exp': jwt.encode({'sub': self.user.profile.public_id, 'type': 'access', 'iat': timezone.now()},
                                 settings.SECRET_KEY, algorithm='HS256'),
            'bad sub': jwt.encode(claims(self.user, sub='abc'), settings.SECRET_KEY, algorithm='HS256'),
            'database id as sub': jwt.encode(claims(self.user, sub=str(self.user.pk)), settings.SECRET_KEY,
                                             algorithm='HS256'),
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


class PublicIdInTokensTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')

    def test_sub_is_public_id_from_me(self):
        token = AccessTokenService().issue(self.user)
        sub = jwt.decode(token, options={'verify_signature': False})['sub']  # what any client can read
        me = self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {token}').json()
        self.assertEqual(sub, me['id'])
        self.assertNotEqual(sub, str(self.user.pk))

    def test_reissued_user_link_invalidates_old_access_and_email_links(self):
        token = AccessTokenService().issue(self.user)
        email_token = EmailTokenService().make(self.user, 'confirm')
        old_id = self.user.profile.public_id
        self.user.profile.reissue_link()
        self.assertEqual(self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {token}').status_code, 401)
        with self.assertRaises(InvalidEmailToken):
            EmailTokenService().read(email_token, 'confirm')
        fresh = AccessTokenService().issue(User.objects.get(pk=self.user.pk))
        me = self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {fresh}').json()
        self.assertNotEqual(me['id'], old_id)

    def test_email_token_has_no_database_id(self):
        payload = signing.loads(EmailTokenService().make(self.user, 'confirm'), salt=EmailTokenService.salt)
        self.assertEqual(payload['uid'], self.user.profile.public_id)
