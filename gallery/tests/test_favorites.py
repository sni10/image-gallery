import tempfile

from django.contrib.auth.models import User
from django.db import IntegrityError, connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from accounts.services.access_tokens import AccessTokenService

from ..models import Favorite
from ..services import PhotoService
from .utils import gallery, jpeg


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp())
class FavoritesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anna = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        cls.bob = User.objects.create_user('bob@example.com', 'bob@example.com', 'x')
        cls.gallery = gallery('G')
        service = PhotoService()
        cls.a, cls.b, cls.c = (service.create(jpeg(100 + i, 100), cls.gallery, f'p{i}') for i in range(3))

    def auth(self, user):
        return {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(user)}'}

    def put(self, photo_id, user=None):
        return self.client.put(f'/me/favorites/{photo_id}', **self.auth(user or self.anna))

    def delete(self, photo_id, user=None):
        return self.client.delete(f'/me/favorites/{photo_id}', **self.auth(user or self.anna))

    def favorites(self, user=None, query=''):
        return self.client.get(f'/me/favorites{query}', **self.auth(user or self.anna))

    def ids(self, response):
        return [p['id'] for p in response.json()['items']]

    # 6.1 model
    def test_unique_pair_and_cascade(self):
        Favorite.objects.create(user=self.anna, photo=self.a)
        with self.assertRaises(IntegrityError):
            Favorite.objects.create(user=self.anna, photo=self.a)

    def test_deleting_photo_removes_it_from_favorites(self):
        self.put(self.a.public_id)
        self.put(self.b.public_id)
        PhotoService.delete(self.gallery.photos.filter(pk=self.a.pk))
        r = self.favorites()
        self.assertEqual((self.ids(r), r.json()['total']), ([self.b.public_id], 1))

    # 6.2 add / remove
    def test_add_is_idempotent(self):
        self.assertEqual((self.put(self.a.public_id).status_code, self.put(self.a.public_id).status_code), (204, 204))
        self.assertEqual(Favorite.objects.filter(user=self.anna).count(), 1)

    def test_add_unknown_photo(self):
        self.assertEqual(self.put(999999).status_code, 404)

    def test_remove_is_idempotent(self):
        self.put(self.a.public_id)
        self.assertEqual(self.delete(self.a.public_id).status_code, 204)
        self.assertEqual(self.delete(self.a.public_id).status_code, 204)
        self.assertEqual(self.delete(999999).status_code, 204)
        self.assertFalse(Favorite.objects.exists())

    def test_anonymous(self):
        for response in (self.client.put(f'/me/favorites/{self.a.public_id}'), self.client.delete(f'/me/favorites/{self.a.public_id}'),
                         self.client.get('/me/favorites')):
            self.assertEqual(response.status_code, 401)

    # 6.3 list
    def test_list_order_pagination_and_isolation(self):
        self.put(self.a.public_id)
        self.put(self.c.public_id)
        self.put(self.b.public_id, user=self.bob)
        r = self.favorites()
        self.assertEqual((self.ids(r), r.json()['total']), ([self.c.public_id, self.a.public_id], 2))  # newest first
        self.assertTrue(all(p['isFavorite'] for p in r.json()['items']))
        self.assertEqual(self.ids(self.favorites(query='?page=2&limit=1')), [self.a.public_id])
        self.assertEqual(self.favorites(query='?page=9').json(), {'items': [], 'total': 2})
        self.assertEqual(self.favorites(query='?page=0').status_code, 400)
        self.assertEqual(self.ids(self.favorites(user=self.bob)), [self.b.public_id])

    # 6.4 isFavorite everywhere
    def test_is_favorite_in_all_photo_responses(self):
        self.put(self.a.public_id)
        self.gallery.cover = self.a
        self.gallery.save()
        urls = [f'/galleries/{self.gallery.public_id}/photos', '/photos?seed=abc']
        for url in urls:
            with self.subTest(url=url):
                flags = {p['id']: p['isFavorite'] for p in self.client.get(url, **self.auth(self.anna)).json()['items']}
                self.assertEqual(flags, {self.a.public_id: True, self.b.public_id: False, self.c.public_id: False})
                anonymous = self.client.get(url).json()['items']
                self.assertFalse(any(p['isFavorite'] for p in anonymous))
                bobs = self.client.get(url, **self.auth(self.bob)).json()['items']
                self.assertFalse(any(p['isFavorite'] for p in bobs))
        cover = self.client.get(f'/galleries/{self.gallery.public_id}', **self.auth(self.anna)).json()['cover']
        self.assertTrue(cover['isFavorite'])
        catalog_cover = self.client.get('/galleries', **self.auth(self.anna)).json()['items'][0]['cover']
        self.assertTrue(catalog_cover['isFavorite'])
        self.assertFalse(self.client.get(f'/galleries/{self.gallery.public_id}').json()['cover']['isFavorite'])

    def test_no_n_plus_one(self):
        def queries_for_list():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(f'/galleries/{self.gallery.public_id}/photos', **self.auth(self.anna))
            return len(ctx.captured_queries)

        before = queries_for_list()
        for i in range(5):
            photo = PhotoService().create(jpeg(200 + i, 100), self.gallery)
            self.put(photo.public_id)
        self.assertEqual(queries_for_list(), before)
