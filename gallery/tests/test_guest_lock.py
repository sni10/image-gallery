import tempfile
import time
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.services.access_tokens import AccessTokenService
from accounts.throttling import OriginalsBurstThrottle

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

    def test_home_feed_guest_sees_ten_positions_from_gallery_open_photos(self):
        other = gallery('Other')
        for i in range(12):
            PhotoService().create(jpeg(60 + i, 20), other)
        gallery_open = {p['id'] for g in (self.g, other)
                        for p in self.items(f'/galleries/{g.public_id}/photos?limit=20') if not p['locked']}
        self.assertEqual(len(gallery_open), 20)

        seen = set()
        for seed in ('a', 'b', 'c', 'zz9'):
            feed = [p for page in (1, 2, 3, 4, 5) for p in self.items(f'/photos?seed={seed}&limit=5&page={page}')]
            self.assertEqual(len({p['id'] for p in feed}), 24)  # pages continue the feed, no repeats or gaps
            self.assertEqual([p['locked'] for p in feed], [False] * 10 + [True] * 14)
            self.assertTrue(all(p['url'] for p in feed[:10]))
            self.assertTrue(all(p['url'] is None and p['thumbUrl'] for p in feed[10:]))
            seen |= {p['id'] for p in feed[:10]}
        self.assertLessEqual(seen, gallery_open)  # trying seeds never opens a photo locked in its gallery

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

    def test_mass_download_limited_per_ip(self):
        cache.clear()  # throttle counters
        self.addCleanup(cache.clear)
        uri = f'{self.path}?{self.query}'
        with patch.object(OriginalsBurstThrottle, 'THROTTLE_RATES', {'original_burst': '3/min', 'original': '100/hour'}):
            codes = [self.check(uri) for _ in range(4)]
            other_ip = self.client.get('/internal/media-auth', HTTP_X_FORWARDED_URI=uri,
                                       HTTP_X_FORWARDED_FOR='10.0.0.2').status_code
        self.assertEqual((codes, other_ip), ([204, 204, 204, 429], 204))

    def test_link_stable_within_an_hour(self):
        hour = 3600 * 500_000
        self.assertEqual(signed_query('/p', now=hour + 10), signed_query('/p', now=hour + 3500))
        self.assertNotEqual(signed_query('/p', now=hour + 10), signed_query('/p', now=hour + 3700))
