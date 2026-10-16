from django.test import TestCase, override_settings

from ..models import Photo, PhotoEmbedding
from .utils import gallery, photo

KEY = 'k' * 64
URL = '/ingest/embeddings'


def vec(x=0.1):
    return [x] * PhotoEmbedding.DIMENSIONS


@override_settings(INGEST_API_KEY=KEY, MEDIA_URL='/media/')
class EmbeddingApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        g = gallery()
        cls.a, cls.b, cls.c = (Photo.objects.create(gallery=g, image=f'original/{n}.jpg', thumb=f'thumb/{n}.webp')
                               for n in 'abc')
        photo(g)  # no thumbnail: nothing to embed
        PhotoEmbedding.objects.create(photo=cls.c, model='siglip2', vector=vec())

    def get(self, key=KEY, **params):
        return self.client.get(URL, params, headers={'X-Api-Key': key})

    def post(self, body, key=KEY):
        return self.client.post(URL, body, content_type='application/json', headers={'X-Api-Key': key})

    def test_missing_lists_photos_without_vector_of_that_model(self):
        r = self.get(model='siglip2')
        self.assertEqual(r.json(), {'items': [
            {'id': p.public_id, 'thumbUrl': f'http://testserver/media/{p.thumb.name}'} for p in (self.a, self.b)
        ]})
        self.assertEqual(len(self.get(model='other').json()['items']), 3)  # another model: c is missing too

    def test_save_creates_overwrites_and_reports_unknown(self):
        r = self.post({'model': 'v2', 'items': [{'id': self.a.public_id, 'vector': vec(0.2)},
                                                 {'id': self.c.public_id, 'vector': vec(0.3)},
                                                 {'id': 'gone', 'vector': vec()}]})
        self.assertEqual(r.json(), {'saved': 2, 'unknown': ['gone']})
        self.assertEqual(PhotoEmbedding.objects.get(photo=self.c).model, 'v2')
        self.assertAlmostEqual(float(PhotoEmbedding.objects.get(photo=self.a).vector[0]), 0.2, places=5)
        self.assertEqual([i['id'] for i in self.get(model='v2').json()['items']], [self.b.public_id])

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
        self.assertEqual(self.get().status_code, 400)  # no model
        self.assertEqual(PhotoEmbedding.objects.count(), 1)

    def test_key_required(self):
        self.assertEqual(self.get(key='wrong', model='m').status_code, 403)
        self.assertEqual(self.post({'model': 'm', 'items': [{'id': self.a.public_id, 'vector': vec()}]},
                                   key='wrong').status_code, 403)
