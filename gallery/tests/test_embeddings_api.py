from django.test import TestCase, override_settings

from ..models import PhotoEmbedding
from .utils import gallery, photo

KEY = 'k' * 64
URL = '/ingest/embeddings'


def vec(x=0.1):
    return [x] * PhotoEmbedding.DIMENSIONS


@override_settings(INGEST_API_KEY=KEY)
class EmbeddingApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        g = gallery()
        cls.a, cls.b = photo(g), photo(g)
        PhotoEmbedding.objects.create(photo=cls.b, model='old', vector=vec())

    def post(self, body, key=KEY):
        return self.client.post(URL, body, content_type='application/json', headers={'X-Api-Key': key})

    def test_save_creates_overwrites_and_reports_unknown(self):
        r = self.post({'model': 'v2', 'items': [{'id': self.a.public_id, 'vector': vec(0.2)},
                                                 {'id': self.b.public_id, 'vector': vec(0.3)},
                                                 {'id': 'gone', 'vector': vec()}]})
        self.assertEqual(r.json(), {'saved': 2, 'unknown': ['gone']})
        a, b = (PhotoEmbedding.objects.get(photo=p) for p in (self.a, self.b))
        self.assertEqual((a.model, b.model), ('v2', 'v2'))
        self.assertAlmostEqual(float(a.vector[0]), 0.2, places=5)
        self.assertAlmostEqual(float(b.vector[0]), 0.3, places=5)

    def test_bad_input_is_400(self):
        cases = [
            {'model': 'm', 'items': [{'id': self.a.public_id, 'vector': [0.1] * 767}]},
            {'model': 'm', 'items': [{'id': self.a.public_id, 'vector': ['NaN'] + [0.1] * 767}]},
            {'model': 'm', 'items': []},
            {'items': [{'id': self.a.public_id, 'vector': vec()}]},
        ]
        for body in cases:
            with self.subTest(body=str(body)[:60]):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(PhotoEmbedding.objects.count(), 1)

    def test_key_required(self):
        body = {'model': 'm', 'items': [{'id': self.a.public_id, 'vector': vec()}]}
        self.assertEqual(self.post(body, key='wrong').status_code, 403)
        self.assertFalse(PhotoEmbedding.objects.filter(photo=self.a).exists())
