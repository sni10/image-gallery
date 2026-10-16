import math
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from ..models import Favorite, PhotoEmbedding
from .utils import bearer, gallery, photo

MODEL = 'siglip2-vit-b-16'


def embed(p, angle, model=MODEL):
    """A unit vector in the plane of the first two axes: the cosine of two photos = cos(angle difference)."""
    vector = [math.cos(angle), math.sin(angle)] + [0.0] * (PhotoEmbedding.DIMENSIONS - 2)
    PhotoEmbedding.objects.create(photo=p, model=model, vector=vector)
    return p


def ids(response):
    return [p['id'] for p in response.json()['items']]


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class SimilarByVectorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.p = embed(photo(gallery('Own'), ['cat']), 0)
        cls.duplicate = embed(photo(gallery('Dup')), 0.05)  # cos 0.999: the same picture
        cls.near = embed(photo(gallery('Near')), 0.5)  # cos 0.878, no shared tags
        cls.tagged = embed(photo(gallery('Tagged'), ['cat']), 0.55)  # a bit farther, but shares the tag
        cls.far = embed(photo(gallery('Far')), 1.4)
        cls.other_model = embed(photo(gallery('Other model')), 0.3, model='old')
        cls.set = gallery('Set')
        cls.same_set = [embed(photo(cls.set), 0.7 + i / 100) for i in range(4)]  # one photo set: at most 3
        cls.no_vector = photo(gallery('Tags only'), ['cat'])

    def similar(self, p, limit=24):
        r = self.client.get(f'/photos/{p.public_id}/similar?limit={limit}')
        self.assertEqual(r.status_code, 200)
        return ids(r)

    def test_order(self):
        got = self.similar(self.p, limit=5)
        self.assertEqual(got, [x.public_id for x in [self.tagged, self.near, *self.same_set[:3]]])

    def test_rules(self):
        got = self.similar(self.p)
        self.assertNotIn(self.duplicate.public_id, got)
        self.assertEqual(sum(x.public_id in got for x in self.same_set), 3)  # the tag filler doesn't add the 4th
        self.assertEqual(len(got), len(set(got)))
        # vectors first, then the tag filler: photos without a vector and of another model
        self.assertLess(got.index(self.far.public_id), got.index(self.no_vector.public_id))
        self.assertIn(self.other_model.public_id, got[got.index(self.far.public_id):])

    def test_no_vector_falls_back_to_tags(self):
        self.assertEqual(self.similar(self.no_vector, limit=2), [self.tagged.public_id, self.p.public_id])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class WaveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        cls.favorites = [embed(photo(gallery(f'Fav {i}')), a) for i, a in enumerate((0, 0.4, 0.8))]
        cls.duplicate = embed(photo(gallery('Dup')), -0.05)  # near-duplicate of a favorite
        cls.candidates = [embed(photo(gallery(f'C {i}')), 1.5 + i / 10) for i in range(10)]
        cls.no_vector = photo(gallery('No vector'))

    def wave(self, user=None, **body):
        return self.client.post('/me/wave', body, content_type='application/json',
                                **bearer(user or self.user))

    def like_all(self):
        for p in self.favorites:
            Favorite.objects.create(user=self.user, photo=p)

    def test_auth_and_validation(self):
        self.assertEqual(self.client.post('/me/wave', {}, content_type='application/json').status_code, 401)
        self.assertEqual(self.wave(exclude=['x'] * 2001).status_code, 400)
        for limit in (0, 49, 'x'):
            with self.subTest(limit=limit):
                self.assertEqual(self.wave(limit=limit).status_code, 400)

    def test_cold_start(self):
        other = User.objects.create_user('o@example.com', 'o@example.com', 'x')
        Favorite.objects.create(user=other, photo=self.candidates[5])
        r = self.wave(limit=4)
        self.assertEqual(r.status_code, 200)
        got = ids(r)
        self.assertEqual((len(got), len(set(got)), got[0]), (4, 4, self.candidates[5].public_id))  # popular first

    def test_by_favorites(self):
        self.like_all()
        got = ids(self.wave(limit=7))  # 7 places: no random one yet
        favorites = {p.public_id for p in self.favorites}
        self.assertEqual(len(got), 7)
        self.assertTrue(set(got) <= {p.public_id for p in self.candidates})  # no favorites, no duplicate, no vectorless
        self.assertNotIn(self.duplicate.public_id, got)
        self.assertFalse(favorites & set(got))

    def test_exclude_pages_until_empty(self):
        self.like_all()
        seen = []
        while page := ids(self.wave(exclude=seen, limit=4)):
            self.assertFalse(set(page) & set(seen))
            seen += page
        # everything with a vector except the favorites and their near-duplicate
        self.assertEqual(set(seen), {p.public_id for p in self.candidates})
