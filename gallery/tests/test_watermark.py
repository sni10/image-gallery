import tempfile
from io import BytesIO
from pathlib import Path

from django.test import SimpleTestCase
from PIL import Image

from ..services.watermark import backfill, watermark


def encode(img, fmt, **kw):
    buf = BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


class WatermarkTest(SimpleTestCase):
    def test_marks_one_corner_with_margin_keeps_format_and_size(self):
        corners = set()
        for shade in range(12):  # different content -> different corners
            data = encode(Image.new('RGB', (800, 600), (shade, 0, 0)), 'PNG')
            out = Image.open(BytesIO(watermark(data))).convert('L')
            self.assertEqual(out.size, (800, 600))
            boxes = {0: (600, 500, 800, 600), 1: (0, 500, 200, 600), 2: (600, 0, 800, 100), 3: (0, 0, 200, 100)}
            marked = [c for c, box in boxes.items() if max(out.crop(box).getdata()) > 100]
            self.assertEqual(len(marked), 1)
            corners.add(marked[0])
            self.assertLess(max(out.crop((0, 0, 800, 5)).getdata()) + max(out.crop((0, 595, 800, 600)).getdata()), 60)  # margin
        self.assertGreater(len(corners), 1)
        self.assertEqual(Image.open(BytesIO(watermark(data))).format, 'PNG')
        self.assertEqual(watermark(data), watermark(data))  # deterministic: content-addressed names stay valid

    def test_orientation_applied_before_marking(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # displayed rotated 90°: 600x800
        out = Image.open(BytesIO(watermark(encode(Image.new('RGB', (800, 600)), 'JPEG', exif=exif))))
        self.assertEqual(out.size, (600, 800))
        self.assertEqual(out.getexif().get(0x0112, 1), 1)

    def test_animated_unchanged(self):
        frames = [Image.new('RGB', (50, 50), c) for c in ('red', 'blue')]
        data = encode(frames[0], 'GIF', save_all=True, append_images=frames[1:])
        self.assertEqual(watermark(data), data)

    def test_backfill_keeps_clean_copy_and_is_rerunnable(self):
        root = Path(tempfile.mkdtemp())
        public, clean = root / 'media/original', root / 'originals/original'
        (public / 'ab/cd').mkdir(parents=True)
        original = encode(Image.new('RGB', (300, 200)), 'PNG')
        (public / 'ab/cd/x.png').write_bytes(original)

        self.assertEqual(backfill(public, clean, dry_run=True)['marked'], 1)
        self.assertFalse(clean.exists())

        self.assertEqual(backfill(public, clean)['marked'], 1)
        self.assertEqual((clean / 'ab/cd/x.png').read_bytes(), original)
        marked = (public / 'ab/cd/x.png').read_bytes()
        self.assertNotEqual(marked, original)

        self.assertEqual(backfill(public, clean)['done'], 1)  # second run touches nothing
        self.assertEqual((public / 'ab/cd/x.png').read_bytes(), marked)
        self.assertEqual(backfill(public, clean, force=True)['marked'], 1)  # re-render from clean, not twice-marked
        self.assertEqual((public / 'ab/cd/x.png').read_bytes(), marked)
