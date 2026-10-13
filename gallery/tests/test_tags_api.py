import tempfile

from django.test import TestCase, override_settings

from .utils import gallery, photo


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class TagListApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        g = gallery()
        for tags in (['dark', 'night', 'neon'], ['dark', 'night', 'city'], ['dark', 'night'], ['dark', 'neon'],
                     ['dark', 'city'], ['city'], ['city'], ['cat']):
            photo(g, tags)

    def get(self, query=''):
        return self.client.get(f'/tags{query}')

    def test_related_by_shared_photos_without_itself(self):
        r = self.get('?related=dark')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'items': [
            {'tag': 'night', 'count': 3}, {'tag': 'city', 'count': 2}, {'tag': 'neon', 'count': 2},  # ties by name
        ]})

    def test_top_tags(self):
        self.assertEqual(self.get('?limit=3').json()['items'],
                         [{'tag': 'dark', 'count': 5}, {'tag': 'city', 'count': 4}, {'tag': 'night', 'count': 3}])

    def test_related_normalized_unknown_empty(self):
        expected = self.get('?related=dark').json()
        for related in ('Dark', '%23dark', '%20%23DARK%20'):
            with self.subTest(related=related):
                self.assertEqual(self.get(f'?related={related}').json(), expected)
        self.assertEqual(self.get('?related=nothing').json(), {'items': []})

    def test_bad_params(self):
        for query, field in (('?limit=0', 'limit'), ('?limit=51', 'limit'), ('?limit=x', 'limit'), ('?related=', 'related')):
            with self.subTest(query=query):
                r = self.get(query)
                self.assertEqual(r.status_code, 400)
                self.assertIn(field, r.json())
