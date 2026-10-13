import tempfile

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings

from gallery.models import Complaint, Favorite
from gallery.services import PhotoService
from gallery.tests.utils import gallery, jpeg, make_category

from ..models import Profile, RefreshToken
from .test_auth_api import TERMS, ApiTestCase
from .test_registration import STRONG, link_token

NEW_STRONG = 'another-strong-passphrase'


class ProfileApiTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', STRONG)
        self.tokens = self.login()

    def login(self, email='anna@example.com', password=STRONG):
        return self.post('/auth/login', email=email, password=password).json()

    def auth(self, access=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {access or self.tokens["access"]}'}

    def post_auth(self, url, **data):
        return self.client.post(url, data, content_type='application/json', HTTP_X_FORWARDED_FOR='10.0.0.1',
                                **self.auth())

    def test_me(self):
        r = self.client.get('/me', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['id'], r.json()['email']), (self.user.profile.public_id, 'anna@example.com'))
        self.assertIn('dateJoined', r.json())
        self.assertIs(r.json()['isAdmin'], False)
        self.assertEqual(self.client.get('/me').status_code, 401)

    def test_me_is_admin_for_staff(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True)
        self.assertIs(self.client.get('/me', **self.auth()).json()['isAdmin'], True)

    def test_private_endpoints_need_token(self):
        for url in ('/me/email', '/me/password'):
            with self.subTest(url=url):
                self.assertEqual(self.post(url).status_code, 401)

    def test_change_email_flow(self):
        r = self.post_auth('/me/email', newEmail=' New@Example.com ', password=STRONG)
        self.assertEqual(r.status_code, 202)
        self.assertEqual(mail.outbox[-1].to, ['new@example.com'])
        self.assertEqual(self.client.get('/me', **self.auth()).json()['email'], 'anna@example.com')  # not yet

        token = link_token(mail.outbox[-1], 'confirm-email-change')
        r = self.post('/auth/confirm-email-change', token=token)
        self.assertEqual((r.status_code, r.json()), (200, {'email': 'new@example.com'}))
        self.assertEqual(mail.outbox[-1].to, ['anna@example.com'])  # notice to the old address
        self.assertIn('new@example.com', mail.outbox[-1].body)
        self.assertEqual(self.client.get('/me', **self.auth()).json()['email'], 'new@example.com')
        self.assertEqual(self.post('/auth/login', email='new@example.com', password=STRONG).status_code, 200)
        self.assertEqual(self.post('/auth/login', email='anna@example.com', password=STRONG).status_code, 401)

        self.assertEqual(self.post('/auth/confirm-email-change', token=token).status_code, 400)  # reuse

    def test_change_email_errors(self):
        User.objects.create_user('taken@example.com', 'taken@example.com', STRONG)
        cases = [
            ({'newEmail': 'new@example.com', 'password': 'wrong'}, 'password'),
            ({'newEmail': 'taken@example.com', 'password': STRONG}, 'newEmail'),
            ({'newEmail': 'no-at-sign', 'password': STRONG}, 'newEmail'),
            ({'newEmail': 'anna@example.com', 'password': STRONG}, 'newEmail'),
        ]
        for data, field in cases:
            with self.subTest(data=data):
                r = self.post_auth('/me/email', **data)
                self.assertEqual(r.status_code, 400)
                self.assertIn(field, r.json())
        self.assertEqual(mail.outbox, [])

    def test_new_email_taken_before_confirmation(self):
        self.post_auth('/me/email', newEmail='new@example.com', password=STRONG)
        token = link_token(mail.outbox[-1], 'confirm-email-change')
        User.objects.create_user('new@example.com', 'new@example.com', STRONG)
        self.assertEqual(self.post('/auth/confirm-email-change', token=token).status_code, 400)
        self.assertEqual(User.objects.get(pk=self.user.pk).email, 'anna@example.com')

    def test_change_password(self):
        other_session = self.login()
        r = self.post_auth('/me/password', currentPassword=STRONG, newPassword=NEW_STRONG)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {'access', 'refresh'})
        for old in (self.tokens['refresh'], other_session['refresh']):
            self.assertEqual(self.post('/auth/refresh', refresh=old).status_code, 401)
        self.assertEqual(self.post('/auth/refresh', refresh=r.json()['refresh']).status_code, 200)
        self.assertEqual(self.post('/auth/login', email='anna@example.com', password=STRONG).status_code, 401)
        self.assertEqual(self.post('/auth/login', email='anna@example.com', password=NEW_STRONG).status_code, 200)

    def test_change_password_errors(self):
        for data, field in (({'currentPassword': 'wrong', 'newPassword': NEW_STRONG}, 'currentPassword'),
                            ({'currentPassword': STRONG, 'newPassword': '12345678'}, 'newPassword')):
            with self.subTest(field=field):
                r = self.post_auth('/me/password', **data)
                self.assertEqual(r.status_code, 400)
                self.assertIn(field, r.json())
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(STRONG))

    def test_change_password_throttled(self):
        codes = [self.post_auth('/me/password', currentPassword='wrong', newPassword=NEW_STRONG).status_code
                 for _ in range(11)]
        self.assertEqual((codes[:10], codes[10]), ([400] * 10, 429))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp())
class DeleteAccountApiTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', STRONG)
        self.access = self.post('/auth/login', email='anna@example.com', password=STRONG).json()['access']

    def delete(self, password=STRONG, access=None):
        return self.client.delete('/me', {'password': password}, content_type='application/json',
                                  HTTP_X_FORWARDED_FOR='10.0.0.1', HTTP_AUTHORIZATION=f'Bearer {access or self.access}')

    def test_delete_account(self):
        photo = PhotoService().create(jpeg(10, 10), gallery('G', make_category('ai')))
        Favorite.objects.create(user=self.user, photo=photo)
        complaint = Complaint.objects.create(email='anna@example.com', message='x' * 10, user=self.user)
        r = self.delete()
        self.assertEqual((r.status_code, r.content), (204, b''))
        self.assertFalse(User.objects.exists())
        self.assertFalse(Favorite.objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(RefreshToken.objects.exists())
        complaint.refresh_from_db()
        self.assertIsNone(complaint.user)
        # the email is free again
        r = self.post('/auth/register', email='anna@example.com', password=STRONG, **TERMS)
        self.assertEqual(r.status_code, 201)

    def test_nothing_deleted_on_errors(self):
        r = self.delete(password='wrong')
        self.assertEqual((r.status_code, r.json()), (400, {'password': ['Wrong password.']}))
        self.assertEqual(self.client.delete('/me', {'password': STRONG}, content_type='application/json').status_code,
                         401)
        admin = User.objects.create_user('admin@example.com', 'admin@example.com', STRONG, is_staff=True)
        admin_access = self.post('/auth/login', email='admin@example.com', password=STRONG).json()['access']
        self.assertEqual(self.delete(access=admin_access).status_code, 403)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {self.access}').status_code, 200)
