import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .utils import bearer, gallery, make_category, photo


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/', GUEST_FREE_PHOTOS=10)
class SimilarPhotosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        ai, comics = make_category('ai'), make_category('comics')
        own, other, far = gallery('Own', ai), gallery('Other', ai), gallery('Far', comics)
        cls.p = photo(own, ['cat', 'neon', 'city'])
        cls.same_gallery_one_tag = photo(own, ['cat'])
        cls.two_tags = photo(far, ['neon', 'cat', 'dog'])
        cls.one_tag = photo(other, ['city'])
        cls.same_category = photo(other)
        cls.newest_unrelated = photo(far, ['dog'])

    def get(self, photo_id, query='', user=None):
        return self.client.get(f'/photos/{photo_id}/similar{query}', **(bearer(user) if user else {}))

    def ids(self, query=''):
        r = self.get(self.p.public_id, query)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {'items'})
        return [p['id'] for p in r.json()['items']]

    def test_order_and_fill(self):
        expected = [self.two_tags, self.one_tag, self.same_gallery_one_tag, self.same_category, self.newest_unrelated]
        self.assertEqual(self.ids(), [p.public_id for p in expected])  # the photo itself is not included
        self.assertEqual(self.ids('?limit=2'), [self.two_tags.public_id, self.one_tag.public_id])

    def test_errors(self):
        self.assertEqual(self.get('nope').status_code, 404)
        for limit in ('0', '25', 'x'):
            with self.subTest(limit=limit):
                self.assertEqual(self.get(self.p.public_id, f'?limit={limit}').status_code, 400)

    def test_locked_for_guest(self):
        g = gallery('Eleven')
        photos = [photo(g, ['z']) for _ in range(11)]  # the oldest is beyond the 10 a guest sees
        oldest = photos[0].public_id
        guest = {p['id']: p for p in self.get(photos[-1].public_id).json()['items']}
        self.assertEqual((guest[oldest]['locked'], guest[oldest]['url']), (True, None))
        user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        signed_in = {p['id']: p for p in self.get(photos[-1].public_id, user=user).json()['items']}
        self.assertFalse(signed_in[oldest]['locked'])
        self.assertTrue(signed_in[oldest]['url'])
