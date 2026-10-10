import tempfile
import time
from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.services.access_tokens import AccessTokenService

from ..services import PhotoService
from ..services.signed_media import signed_query
from .utils import gallery, jpeg


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class GuestLockTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        cls.g = gallery('Twelve')
        cls.photos = [PhotoService().create(jpeg(20 + i, 20), cls.g) for i in range(12)]  # oldest first
        cls.newest_first = cls.photos[::-1]

    def get(self, path, user=None):
        auth = {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(user)}'} if user else {}
        return self.client.get(path, **auth)

    def items(self, path, user=None):
        return self.get(path, user).json()['items']

    def test_guest_gets_originals_of_ten_newest_in_gallery_counted_across_pages(self):
        items = self.items(f'/galleries/{self.g.public_id}/photos?limit=20')
        self.assertEqual([p['locked'] for p in items], [False] * 10 + [True] * 2)
        self.assertTrue(all(p['url'] for p in items[:10]))
        self.assertEqual([p['url'] for p in items[10:]], [None, None])
        self.assertTrue(all(p['thumbUrl'] for p in items))

        page2 = self.items(f'/galleries/{self.g.public_id}/photos?limit=5&page=2')  # positions 6-10
        page3 = self.items(f'/galleries/{self.g.public_id}/photos?limit=5&page=3')  # positions 11-12
        self.assertEqual([p['locked'] for p in page2 + page3], [False] * 5 + [True] * 2)

    def test_signed_in_user_gets_everything(self):
        items = self.items(f'/galleries/{self.g.public_id}/photos?limit=20', self.user)
        self.assertFalse(any(p['locked'] for p in items))
        self.assertTrue(all(p['url'] for p in items))
        self.assertTrue(all(p['url'] for p in self.items('/photos?seed=a&limit=20', self.user)))

    def test_home_feed_locked_for_guests(self):
        items = self.items('/photos?seed=a&limit=20')
        self.assertEqual(len(items), 12)
        self.assertTrue(all(p['locked'] and p['url'] is None and p['thumbUrl'] for p in items))

    def test_photo_detail_uses_position_in_gallery(self):
        third, eleventh = self.newest_first[2], self.newest_first[10]
        self.assertIsNotNone(self.get(f'/photos/{third.public_id}').json()['url'])
        body = self.get(f'/photos/{eleventh.public_id}').json()
        self.assertEqual((body['url'], body['locked']), (None, True))

    def test_cover_of_locked_photo(self):
        self.g.cover = self.photos[0]  # oldest = 12th in the gallery
        self.g.save()
        cover = self.get(f'/galleries/{self.g.public_id}').json()['cover']
        self.assertEqual((cover['url'], cover['locked']), (None, True))
        self.assertTrue(cover['thumbUrl'])

    def test_locked_photo_without_thumb_leaks_nothing(self):
        photo = self.photos[0]
        photo.thumb = ''
        photo.save()
        response = self.get(f'/photos/{photo.public_id}')
        self.assertEqual((response.json()['url'], response.json()['thumbUrl']), (None, None))
        self.assertNotIn(photo.image.name, response.content.decode())

    def test_responses_vary_on_authorization(self):
        self.assertIn('Authorization', self.get('/photos?seed=a')['Vary'])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class MediaAuthTest(TestCase):
    def setUp(self):
        photo = PhotoService().create(jpeg(20, 20), gallery('G'))
        url = urlsplit(self.client.get(f'/photos/{photo.public_id}').json()['url'])
        self.path, self.query = url.path, url.query

    def check(self, uri):
        return self.client.get('/internal/media-auth', HTTP_X_FORWARDED_URI=uri).status_code

    def test_valid_link(self):
        self.assertIn('exp=', self.query)
        self.assertIn('sig=', self.query)
        self.assertEqual(self.check(f'{self.path}?{self.query}'), 204)

    def test_rejected(self):
        sig = self.query.split('sig=')[1]
        bad = self.query.replace(sig, ('0' if sig[0] != '0' else '1') + sig[1:])
        expired = signed_query(self.path, now=time.time() - 10 * 3600)
        for uri in (f'{self.path}?{bad}', f'/media/original/00/00/other.jpg?{self.query}',
                    f'{self.path}?{expired}', self.path, ''):
            self.assertEqual(self.check(uri), 403, uri)

    def test_link_stable_within_an_hour(self):
        hour = 3600 * 500_000
        self.assertEqual(signed_query('/p', now=hour + 10), signed_query('/p', now=hour + 3500))
        self.assertNotEqual(signed_query('/p', now=hour + 10), signed_query('/p', now=hour + 3700))
