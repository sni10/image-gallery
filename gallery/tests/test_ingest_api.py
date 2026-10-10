import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image, PngImagePlugin

from ..models import Gallery, Photo
from .utils import gallery, image, jpeg, make_category

KEY = 'k' * 64


def comfy_png(color=(10, 20, 30)):
    info = PngImagePlugin.PngInfo()
    info.add_text('prompt', f'{{"api_key": "{KEY}"}}')
    buf = BytesIO()
    Image.new('RGB', (64, 48), color).save(buf, 'PNG', pnginfo=info)
    return SimpleUploadedFile('ComfyUI_00042_.png', buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/', INGEST_API_KEY=KEY)
class PhotoIngestApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = make_category('ai')
        cls.gallery = gallery('Existing', cls.category)

    def post(self, key=KEY, **data):
        headers = {'X-Api-Key': key} if key is not None else {}
        return self.client.post('/ingest/photos', data, headers=headers)

    def test_key_required(self):
        for key in (None, '', 'wrong', KEY[:-1]):
            with self.subTest(key=key):
                self.assertEqual(self.post(key, image=jpeg(10, 10), gallery=self.gallery.public_id).status_code, 403)
        with override_settings(INGEST_API_KEY=''):  # not configured: off even for an empty header
            self.assertEqual(self.post('', image=jpeg(10, 10), gallery=self.gallery.public_id).status_code, 403)
        self.assertFalse(Photo.objects.exists())

    def test_bearer_header_ignored(self):
        response = self.client.post('/ingest/photos', {'image': jpeg(10, 10), 'gallery': self.gallery.public_id},
                                    headers={'X-Api-Key': KEY, 'Authorization': 'Bearer not-a-jwt'})
        self.assertEqual(response.status_code, 201)

    def test_upload_to_gallery_by_id(self):
        response = self.post(image=comfy_png(), gallery=self.gallery.public_id, title='Neon Fox',
                             description='A fox.\nIn neon.', tags='#Fox, neon\ncyberpunk, fox, ')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        photo = Photo.objects.get()
        self.assertEqual(body['gallery'], {'id': self.gallery.public_id, 'title': 'Existing', 'category': 'ai'})
        self.assertEqual(body['photo']['id'], photo.public_id)
        self.assertEqual((body['photo']['title'], body['photo']['description'], body['photo']['tags'], body['photo']['isFavorite']),
                         ('Neon Fox', 'A fox.\nIn neon.', ['fox', 'neon', 'cyberpunk'], False))
        self.assertEqual((photo.gallery, photo.tags, photo.width, photo.height), (self.gallery, ['fox', 'neon', 'cyberpunk'], 64, 48))
        self.assertTrue(photo.thumb.name.endswith('.webp'))
        self.assertNotIn(KEY.encode(), photo.image.read())  # ComfyUI metadata stripped

    def test_empty_title_is_file_name(self):
        self.post(image=comfy_png(), gallery=self.gallery.public_id)
        self.assertEqual((Photo.objects.get().title, Photo.objects.get().tags), ('ComfyUI_00042_', []))

    def test_gallery_by_category_and_title_created_once(self):
        first = self.post(image=comfy_png((1, 1, 1)), category='ai', galleryTitle='AI 2026-10')
        second = self.post(image=comfy_png((2, 2, 2)), category='ai', galleryTitle='AI 2026-10')
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        created = Gallery.objects.get(title='AI 2026-10')
        self.assertEqual((created.category, created.photos.count()), (self.category, 2))
        self.assertEqual(first.json()['gallery']['id'], created.public_id)

    def test_same_image_twice_is_idempotent(self):
        first = self.post(image=comfy_png(), gallery=self.gallery.public_id, title='First')
        again = self.post(image=comfy_png(), gallery=self.gallery.public_id, title='Second')
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.json()['photo']['id'], first.json()['photo']['id'])
        self.assertEqual(Photo.objects.get().title, 'First')
        # another gallery is another photo (sharing the stored file)
        self.assertEqual(self.post(image=comfy_png(), category='ai', galleryTitle='Other').status_code, 201)

    def test_unknown_gallery_or_category(self):
        self.assertEqual(self.post(image=jpeg(10, 10), gallery='a' * 26).status_code, 404)
        self.assertEqual(self.post(image=jpeg(10, 10), category='nope', galleryTitle='X').status_code, 404)
        self.assertFalse(Gallery.objects.filter(title='X').exists())

    def test_gallery_choice_errors(self):
        cases = [
            ({}, 'gallery'),
            ({'gallery': 'x', 'category': 'ai', 'galleryTitle': 'X'}, 'gallery'),
            ({'category': 'ai'}, 'galleryTitle'),
            ({'galleryTitle': 'X'}, 'category'),
        ]
        for fields, error in cases:
            with self.subTest(fields=fields):
                response = self.post(image=jpeg(10, 10), **fields)
                self.assertEqual(response.status_code, 400)
                self.assertIn(error, response.json())

    def test_bad_image(self):
        for upload in (None, image(10, 10, 'x.tif', 'TIFF'), SimpleUploadedFile('x.png', b'not an image')):
            with self.subTest(upload=upload):
                data = {'gallery': self.gallery.public_id, **({'image': upload} if upload else {})}
                response = self.post(**data)
                self.assertEqual(response.status_code, 400)
                self.assertIn('image', response.json())

    def test_field_limits(self):
        cases = [
            ({'tags': ','.join(f't{i}' for i in range(31))}, 'tags'),
            ({'tags': 'x' * 51}, 'tags'),
            ({'title': 'x' * 201}, 'title'),
            ({'description': 'x' * 5001}, 'description'),
        ]
        for fields, error in cases:
            with self.subTest(error=error):
                response = self.post(image=jpeg(10, 10), gallery=self.gallery.public_id, **fields)
                self.assertEqual(response.status_code, 400)
                self.assertIn(error, response.json())
        self.assertEqual(self.post(image=jpeg(10, 10), gallery=self.gallery.public_id,
                                   tags=','.join(f't{i}' for i in range(30))).status_code, 201)

    def test_public_api_shows_description_and_tags(self):
        self.post(image=comfy_png(), gallery=self.gallery.public_id, description='Desc', tags='a, b')
        item = self.client.get(f'/galleries/{self.gallery.public_id}/photos').json()['items'][0]
        self.assertEqual((item['description'], item['tags']), ('Desc', ['a', 'b']))
