import tempfile

from django.test import TestCase, override_settings

from ..services import PhotoService
from .utils import gallery, jpeg


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RandomPhotoApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        service = PhotoService()
        cls.ids = set()
        for g in (gallery('A'), gallery('B'), gallery('C')):
            for i in range(5):
                cls.ids.add(str(service.create(jpeg(100 + i, 50 + len(cls.ids)), g).pk))  # unique content

    def ids_of(self, seed, page, limit=4):
        data = self.client.get(f'/photos?seed={seed}&page={page}&limit={limit}').json()
        self.assertEqual(set(data), {'items', 'total'})
        self.assertEqual(data['total'], 15)
        return [p['id'] for p in data['items']]

    def test_pages_of_one_seed_cover_all_photos_once(self):
        flat = [pid for page in range(1, 5) for pid in self.ids_of('abc', page)]
        self.assertEqual(len(flat), 15)
        self.assertEqual(set(flat), self.ids)  # photos of all galleries, no repeats, nothing skipped

    def test_same_seed_same_order_different_seed_different_order(self):
        self.assertEqual(self.ids_of('abc', 1, 15), self.ids_of('abc', 1, 15))
        self.assertNotEqual(self.ids_of('abc', 1, 15), self.ids_of('xyz', 1, 15))

    def test_invalid_params(self):
        for query in ('', 'seed=', 'seed=bad-seed!', 'seed=abc%0A', 'seed=' + 'a' * 33, 'seed=abc&page=0'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f'/photos?{query}').status_code, 400)
