import re
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.services.access_tokens import AccessTokenService

from ..services import PhotoService
from .utils import gallery, jpeg

PUBLIC_ID = re.compile(r'^[a-z2-7]{26}$')


def all_ids(data):
    """Every value under an "id" key, at any depth of a JSON response."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'id':
                yield value
            yield from all_ids(value)
    elif isinstance(data, list):
        for item in data:
            yield from all_ids(item)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PublicIdApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        cls.gallery = gallery('G')
        cls.photo = PhotoService().create(jpeg(10, 10), cls.gallery)

    def setUp(self):
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(self.user)}'}
        self.client.put(f'/me/favorites/{self.photo.public_id}', **self.auth)

    # 2.1
    def test_no_database_ids_in_any_response(self):
        urls = ['/galleries', '/categories', f'/galleries/{self.gallery.public_id}',
                f'/galleries/{self.gallery.public_id}/photos', '/photos?seed=abc', '/me', '/me/favorites']
        for url in urls:
            with self.subTest(url=url):
                r = self.client.get(url, **self.auth)
                self.assertEqual(r.status_code, 200)
                ids = list(all_ids(r.json()))
                self.assertTrue(ids)
                for value in ids:
                    self.assertRegex(value, PUBLIC_ID)
        me = self.client.get('/me', **self.auth).json()
        self.assertEqual(me['id'], self.user.profile.public_id)

    # 2.2
    def test_paths_accept_only_public_ids(self):
        g, p = self.gallery, self.photo
        self.assertEqual(self.client.get(f'/galleries/{g.public_id}').status_code, 200)
        self.assertEqual(self.client.get(f'/galleries/{g.public_id}/photos').status_code, 200)
        for bad in (str(g.pk), 'a' * 26, 'unknown'):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.get(f'/galleries/{bad}').status_code, 404)
                self.assertEqual(self.client.get(f'/galleries/{bad}/photos').status_code, 404)
        self.assertEqual(self.client.put(f'/me/favorites/{p.pk}', **self.auth).status_code, 404)
        self.assertEqual(self.client.delete(f'/me/favorites/{p.pk}', **self.auth).status_code, 204)
        self.assertTrue(self.user.favorites.filter(photo=p).exists())  # numeric id removed nothing
        self.assertEqual(self.client.delete(f'/me/favorites/{p.public_id}', **self.auth).status_code, 204)
        self.assertFalse(self.user.favorites.exists())
