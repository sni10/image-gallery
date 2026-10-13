import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from ..models import Collection, CollectionPhoto
from ..services import PhotoService
from .utils import bearer, gallery, photo


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class CollectionApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        self.other = User.objects.create_user('o@example.com', 'o@example.com', 'x')
        g = gallery()
        self.p1, self.p2 = photo(g), photo(g)

    def call(self, method, url, user='me', **data):
        user = self.user if user == 'me' else user
        return getattr(self.client, method)(url, data, content_type='application/json',
                                            **(bearer(user) if user else {}))

    def create(self, title='Cats', user='me'):
        r = self.call('post', '/me/collections', user, title=title)
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()['id']

    def test_crud(self):
        cid = self.create('  Cats  ')
        self.assertEqual(self.call('get', f'/me/collections/{cid}').json(), {'id': cid, 'title': 'Cats', 'photosCount': 0})

        self.assertEqual(self.call('put', f'/me/collections/{cid}/photos/{self.p1.public_id}').status_code, 204)
        self.assertEqual(self.call('put', f'/me/collections/{cid}/photos/{self.p2.public_id}').status_code, 204)
        self.assertEqual(self.call('put', f'/me/collections/{cid}/photos/{self.p1.public_id}').status_code, 204)  # again
        self.assertEqual(self.call('put', f'/me/collections/{cid}/photos/nope').status_code, 404)

        r = self.call('patch', f'/me/collections/{cid}', title='Dogs')
        self.assertEqual((r.status_code, r.json()['title'], r.json()['photosCount']), (200, 'Dogs', 2))
        self.assertEqual(r.json()['cover']['id'], self.p2.public_id)  # last added

        page = self.call('get', f'/me/collections/{cid}/photos?limit=1').json()
        self.assertEqual((page['total'], [p['id'] for p in page['items']]), (2, [self.p2.public_id]))

        self.assertEqual(self.call('delete', f'/me/collections/{cid}/photos/{self.p2.public_id}').status_code, 204)
        self.assertEqual(self.call('delete', f'/me/collections/{cid}/photos/{self.p2.public_id}').status_code, 204)
        self.assertEqual(self.call('get', f'/me/collections/{cid}').json()['photosCount'], 1)

        self.assertEqual(self.call('delete', f'/me/collections/{cid}').status_code, 204)
        self.assertEqual(self.call('get', f'/me/collections/{cid}').status_code, 404)
        self.assertTrue(self.p1.__class__.objects.filter(pk=self.p1.pk).exists())  # photos stay

    def test_list_order_cover_and_has_photo(self):
        old, new = self.create('Old'), self.create('New')
        self.call('put', f'/me/collections/{old}/photos/{self.p1.public_id}')  # touching moves it up
        self.create('Foreign', user=self.other)
        items = self.call('get', '/me/collections').json()
        self.assertEqual([c['id'] for c in items], [old, new])
        self.assertEqual((items[0]['cover']['id'], items[1]['cover']), (self.p1.public_id, None))
        self.assertNotIn('hasPhoto', items[0])
        items = self.call('get', f'/me/collections?photo={self.p1.public_id}').json()
        self.assertEqual([c['hasPhoto'] for c in items], [True, False])

    def test_title_validation(self):
        for title in ('', '   ', 'x' * 101):
            with self.subTest(title=title):
                r = self.call('post', '/me/collections', title=title)
                self.assertEqual(r.status_code, 400)
                self.assertIn('title', r.json())

    def test_foreign_collection_is_404_everywhere(self):
        cid = self.create(user=self.other)
        p = self.p1.public_id
        for method, url in (('get', f'/me/collections/{cid}'), ('patch', f'/me/collections/{cid}'),
                            ('delete', f'/me/collections/{cid}'), ('get', f'/me/collections/{cid}/photos'),
                            ('put', f'/me/collections/{cid}/photos/{p}'), ('delete', f'/me/collections/{cid}/photos/{p}')):
            with self.subTest(method=method, url=url):
                self.assertEqual(self.call(method, url, title='Mine').status_code, 404)
                self.assertEqual(self.call(method, url, user=None, title='Mine').status_code, 401)
        self.assertEqual(Collection.objects.get().title, 'Cats')
        self.assertFalse(CollectionPhoto.objects.exists())

    def test_limits(self):
        with mock.patch.object(Collection, 'MAX_PER_USER', 1), mock.patch.object(Collection, 'MAX_PHOTOS', 1):
            cid = self.create()
            r = self.call('post', '/me/collections', title='Second')
            self.assertEqual((r.status_code, r.json()['code']), (400, 'limit'))
            self.call('put', f'/me/collections/{cid}/photos/{self.p1.public_id}')
            r = self.call('put', f'/me/collections/{cid}/photos/{self.p2.public_id}')
            self.assertEqual((r.status_code, r.json()['code']), (400, 'limit'))
            self.assertEqual(self.call('put', f'/me/collections/{cid}/photos/{self.p1.public_id}').status_code, 204)

    def test_cascades(self):
        cid = self.create()
        self.call('put', f'/me/collections/{cid}/photos/{self.p1.public_id}')
        PhotoService.delete(self.p1.__class__.objects.filter(pk=self.p1.pk))
        self.assertEqual(self.call('get', f'/me/collections/{cid}').json()['photosCount'], 0)
        self.user.delete()
        self.assertFalse(Collection.objects.exists())
