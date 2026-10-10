import tempfile

from django.test import TestCase, override_settings

from ..services import PhotoService
from .utils import gallery, jpeg, make_category


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp(), FRONTEND_URL='https://artai.win')
class SitemapTest(TestCase):
    def test_lists_frontend_pages_with_photos_only(self):
        full = gallery('Full', make_category('ai'))
        photo = PhotoService().create(jpeg(10, 10), full)
        empty = gallery('Empty', make_category('comics'))

        r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        for path in ('/', '/galleries', '/categories/ai', f'/galleries/{full.public_id}', f'/photos/{photo.public_id}'):
            self.assertIn(f'<loc>https://artai.win{path}</loc>', body)
        self.assertNotIn(empty.public_id, body)
        self.assertNotIn('/categories/comics', body)
        self.assertNotIn('testserver', body)
