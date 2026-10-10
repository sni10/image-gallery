import tempfile
from io import BytesIO

from django.test import SimpleTestCase, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageCms, PngImagePlugin

from ..services import ImageProcessor, PhotoService
from ..services.metadata import ORIENTATION, strip_metadata
from .utils import gallery

def icc_profile():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


def exif(orientation=None, gps=True):
    data = Image.Exif()
    data[0x010F] = 'SecretCam'  # Make
    if orientation:
        data[ORIENTATION] = orientation
    if gps:
        data[0x8825] = {2: (55.0, 45.0, 0.0)}  # GPSInfo: latitude
    return data


def encode(fmt, mode='RGB', size=(64, 48), **kwargs):
    buf = BytesIO()
    img = Image.new(mode, size, (200, 30, 90) if mode == 'RGB' else None)
    img.save(buf, fmt, **kwargs)
    return buf.getvalue()


def comfy_png(**kwargs):
    info = PngImagePlugin.PngInfo()
    info.add_text('prompt', '{"api_key": "SECRET-KEY"}')
    info.add_itxt('workflow', '{"nodes": ["SECRET-KEY"]}')
    info.add_text('Comment', 'compressed SECRET-KEY', zip=True)
    return encode('PNG', pnginfo=info, **kwargs)


def pixels(data):
    with Image.open(BytesIO(data)) as img:
        return img.convert('RGBA').tobytes()


def info_of(data):
    with Image.open(BytesIO(data)) as img:
        return img.info, img.getexif(), img.format


class StripMetadataTest(SimpleTestCase):
    def assertClean(self, data, fmt):
        clean = strip_metadata(data, fmt)
        self.assertNotIn(b'SECRET', clean)
        self.assertNotIn(b'SecretCam', clean)
        self.assertEqual(pixels(clean), pixels(data))
        self.assertEqual(strip_metadata(clean, fmt), clean)  # idempotent: names are content hashes
        return clean

    def test_png_text_removed_icc_kept(self):
        clean = self.assertClean(comfy_png(icc_profile=icc_profile(), exif=exif()), 'PNG')
        info, exif_data, _ = info_of(clean)
        self.assertEqual(info.get('icc_profile'), icc_profile())
        self.assertNotIn('prompt', info)
        self.assertEqual(dict(exif_data), {})

    def test_png_orientation_kept(self):
        clean = self.assertClean(encode('PNG', exif=exif(orientation=6)), 'PNG')
        self.assertEqual(dict(info_of(clean)[1]), {ORIENTATION: 6})

    def test_jpeg_exif_removed_without_reencoding(self):
        data = encode('JPEG', exif=exif(), icc_profile=icc_profile(), comment=b'SECRET comment')
        clean = self.assertClean(data, 'JPEG')
        info, exif_data, _ = info_of(clean)
        self.assertEqual((dict(exif_data), info.get('icc_profile')), ({}, icc_profile()))
        # same entropy-coded data: from SOS to the end
        self.assertEqual(clean[clean.index(b'\xff\xda'):], data[data.index(b'\xff\xda'):])

    def test_jpeg_orientation_kept_and_xmp_removed(self):
        data = encode('JPEG', exif=exif(orientation=6), xmp=b'<x:xmpmeta>SECRET</x:xmpmeta>')
        clean = self.assertClean(data, 'JPEG')
        self.assertEqual(dict(info_of(clean)[1]), {ORIENTATION: 6})

    def test_jpeg_trailing_data_dropped(self):
        data = encode('JPEG')
        self.assertEqual(strip_metadata(data + b'SECRET trailer', 'JPEG'), data)

    def test_clean_jpeg_untouched(self):
        data = encode('JPEG')
        self.assertEqual(strip_metadata(data, 'JPEG'), data)

    def test_webp(self):
        for kwargs in ({'lossless': True}, {'quality': 80}):
            with self.subTest(**kwargs):
                data = encode('WEBP', exif=exif(orientation=3), xmp=b'<x>SECRET</x>', icc_profile=icc_profile(), **kwargs)
                clean = self.assertClean(data, 'WEBP')
                info, exif_data, fmt = info_of(clean)
                self.assertEqual((fmt, dict(exif_data), info.get('icc_profile')), ('WEBP', {ORIENTATION: 3}, icc_profile()))
                self.assertNotIn('xmp', info)

    def test_gif_comment_removed_loop_kept(self):
        frames = [Image.new('RGB', (8, 8), color) for color in ('red', 'green', 'blue')]
        buf = BytesIO()
        frames[0].save(buf, 'GIF', save_all=True, append_images=frames[1:], loop=0, comment=b'SECRET', duration=50)
        clean = self.assertClean(buf.getvalue(), 'GIF')
        with Image.open(BytesIO(clean)) as img:
            self.assertEqual((img.n_frames, img.info.get('loop')), (3, 0))
            self.assertNotIn('comment', img.info)

    def test_avif_reencoded_only_with_metadata(self):
        plain = encode('AVIF')
        self.assertEqual(strip_metadata(plain, 'AVIF'), plain)
        clean = strip_metadata(encode('AVIF', exif=exif(orientation=6), xmp=b'<x>SECRET</x>'), 'AVIF')
        self.assertNotIn(b'SECRET', clean)
        self.assertNotIn(b'SecretCam', clean)
        self.assertEqual(dict(info_of(clean)[1]), {ORIENTATION: 6})

    def test_broken_file(self):
        with self.assertRaises(ValueError):
            strip_metadata(encode('PNG')[:40], 'PNG')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp())
class StoredOriginalTest(TestCase):
    def test_original_stored_without_metadata(self):
        photo = PhotoService().create(SimpleUploadedFile('comfy.png', comfy_png()), gallery())
        self.assertNotIn(b'SECRET', photo.image.read())

    def test_same_picture_with_other_metadata_stored_once(self):
        g = gallery()
        a = PhotoService().create(SimpleUploadedFile('a.png', comfy_png()), g)
        b = PhotoService().create(SimpleUploadedFile('b.png', encode('PNG')), g)
        self.assertEqual(a.image.name, b.image.name)
        self.assertEqual(ImageProcessor().process(a.image).original, a.image.open('rb').read())
