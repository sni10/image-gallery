from django.test import TestCase, override_settings

from ..models import Photo
from .utils import gallery, photo

KEY = 'k' * 64


@override_settings(INGEST_API_KEY=KEY)
class TextApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.g = gallery()
        cls.p = photo(cls.g, tags=['old'])

    def patch(self, url, body, key=KEY):
        return self.client.patch(url, body, content_type='application/json', headers={'X-Api-Key': key})

    def test_photo_given_fields_replaced(self):
        r = self.patch(f'/ingest/photos/{self.p.public_id}', {'description': 'A neon cat', 'tags': ['#Cat', 'neon', 'cat']})
        self.assertEqual(r.status_code, 204)
        p = Photo.objects.get(pk=self.p.pk)
        self.assertEqual((p.description, p.tags, p.tags_text), ('A neon cat', ['cat', 'neon'], 'cat neon'))
        self.assertEqual(self.patch(f'/ingest/photos/{self.p.public_id}', {'title': 'Cat'}).status_code, 204)
        self.assertEqual(Photo.objects.get(pk=self.p.pk).tags, ['cat', 'neon'])  # not sent: kept

    def test_gallery_description(self):
        self.assertEqual(self.patch(f'/ingest/galleries/{self.g.public_id}', {'description': 'Neon cats'}).status_code, 204)
        self.assertEqual(self.client.get(f'/galleries/{self.g.public_id}').json()['description'], 'Neon cats')

    def test_errors(self):
        url = f'/ingest/photos/{self.p.public_id}'
        self.assertEqual(self.patch(url, {'title': 'x'}, key='wrong').status_code, 403)
        self.assertEqual(self.patch(url, {'tags': ['t'] * 31 + [str(i) for i in range(31)]}).status_code, 400)
        self.assertEqual(self.patch('/ingest/photos/gone', {'title': 'x'}).status_code, 404)
        self.assertEqual(self.patch(f'/ingest/galleries/{self.g.public_id}', {}).status_code, 400)
        self.assertEqual(Photo.objects.get(pk=self.p.pk).title, '')
