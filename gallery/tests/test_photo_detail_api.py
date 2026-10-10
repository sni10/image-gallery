import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.services.access_tokens import AccessTokenService

from ..models import Photo
from ..services import PhotoService
from .utils import gallery, jpeg


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp())
class PhotoDetailApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('admin@example.com', 'admin@example.com', 'x', is_staff=True)
        cls.anna = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        cls.photo = PhotoService().create(jpeg(100, 100), gallery('G'), 'p', 'about', ['cat'])

    def test_get_photo_with_gallery_and_category(self):
        r = self.client.get(f'/photos/{self.photo.public_id}')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body['id'], body['title'], body['description'], body['tags'], body['isFavorite']),
                         (self.photo.public_id, 'p', 'about', ['cat'], False))
        g = self.photo.gallery
        self.assertEqual(body['gallery'], {
            'id': g.public_id, 'title': 'G',
            'category': {'id': g.category.public_id, 'slug': g.category.slug, 'title': g.category.title},
        })
        self.assertTrue(body['thumbUrl'].startswith('http'))

    def test_get_unknown_photo(self):
        self.assertEqual(self.client.get('/photos/nope').status_code, 404)

    def delete(self, user=None, photo_id=None):
        auth = {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(user)}'} if user else {}
        return self.client.delete(f'/photos/{photo_id or self.photo.public_id}', **auth)

    def test_admin_deletes_photo_and_files(self):
        storage, name = self.photo.image.storage, self.photo.image.name
        with self.captureOnCommitCallbacks(execute=True):  # files go after commit
            self.assertEqual(self.delete(self.admin).status_code, 204)
        self.assertFalse(Photo.objects.filter(pk=self.photo.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_admin_unknown_photo(self):
        self.assertEqual(self.delete(self.admin, 'nope').status_code, 404)

    def test_not_admin(self):
        self.assertEqual(self.delete(self.anna).status_code, 403)
        self.assertEqual(self.delete().status_code, 401)
        self.assertTrue(Photo.objects.filter(pk=self.photo.pk).exists())
