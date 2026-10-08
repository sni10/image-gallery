import hashlib
import tempfile
from io import BytesIO, StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from ..services import ImageProcessor, PhotoService, UnsupportedImageFormat
from .utils import gallery, image, jpeg


def rotated_jpeg(w, h):
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° -> displayed as h x w
    return image(w, h, 'rotated.jpg', exif=exif)


def open_bytes(data):
    return Image.open(BytesIO(data))


class ImageProcessorTest(TestCase):
    def test_original_size_and_webp_thumb(self):
        result = ImageProcessor().process(jpeg(4000, 3000))
        self.assertEqual((result.extension, result.width, result.height), ('jpg', 4000, 3000))
        thumb = open_bytes(result.thumb)
        self.assertEqual((thumb.format, thumb.size), ('WEBP', (400, 300)))

    def test_exif_orientation_applied_to_size(self):
        result = ImageProcessor().process(rotated_jpeg(400, 300))
        self.assertEqual((result.width, result.height), (300, 400))

    def test_png_keeps_transparency_in_thumb(self):
        result = ImageProcessor().process(image(800, 800, 'a.png', 'PNG', 'RGBA'))
        self.assertEqual(result.extension, 'png')
        self.assertEqual(open_bytes(result.thumb).mode, 'RGBA')

    def test_small_image_not_upscaled(self):
        self.assertEqual(open_bytes(ImageProcessor().process(jpeg(300, 200)).thumb).size, (300, 200))

    def test_unsupported_format(self):
        with self.assertRaises(UnsupportedImageFormat):
            ImageProcessor().process(image(10, 10, 'x.tif', 'TIFF'))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PhotoServiceTest(TestCase):
    def setUp(self):
        self.gallery = gallery()

    def test_original_stored_untouched_and_named_by_hash(self):
        upload = jpeg(4000, 3000, 'big.jpg')
        original_bytes = upload.read()
        photo = PhotoService().create(upload, self.gallery)
        digest = hashlib.sha256(original_bytes).hexdigest()
        path = f'{digest[:2]}/{digest[2:4]}/{digest}'

        self.assertEqual(photo.image.name, f'original/{path}.jpg')
        self.assertEqual(photo.image.read(), original_bytes)
        self.assertEqual(photo.thumb.name, f'thumb/{path}.webp')
        self.assertEqual(Image.open(photo.thumb).size, (400, 300))
        self.assertEqual((photo.title, photo.width, photo.height), ('big', 4000, 3000))

    def test_keeps_original_format(self):
        photo = PhotoService().create(image(50, 50, 'logo.png', 'PNG'), self.gallery)
        self.assertTrue(photo.image.name.endswith('.png'))

    def test_different_content_different_names(self):
        a = PhotoService().create(jpeg(800, 600, 'same.jpg'), self.gallery)
        b = PhotoService().create(jpeg(600, 800, 'same.jpg'), self.gallery)
        self.assertNotEqual(a.image.name, b.image.name)

    def test_same_content_stored_once(self):
        a = PhotoService().create(jpeg(800, 600, 'one.jpg'), self.gallery)
        b = PhotoService().create(jpeg(800, 600, 'copy.jpg'), self.gallery)
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual((a.image.name, a.thumb.name), (b.image.name, b.thumb.name))  # no _AbC123 duplicates

    def test_rebuild_thumbs_command(self):
        photo = PhotoService().create(rotated_jpeg(800, 600), self.gallery)
        photo.thumb.save('old.jpg', ContentFile(b'x'), save=False)
        photo.width = photo.height = 0
        photo.save()

        call_command('rebuild_thumbs', stdout=StringIO())
        photo.refresh_from_db()
        self.assertTrue(photo.thumb.name.endswith('.webp'))
        self.assertEqual(Image.open(photo.thumb).format, 'WEBP')
        self.assertEqual((photo.width, photo.height), (600, 800))
