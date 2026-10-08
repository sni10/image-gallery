from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

# Formats browsers can display, so the original can be served as is -> file extension
SUPPORTED_FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif', 'AVIF': 'avif'}


class UnsupportedImageFormat(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    extension: str  # of the original, from SUPPORTED_FORMATS
    width: int      # size of the original as displayed (EXIF orientation applied)
    height: int
    thumb: bytes    # WebP


class ImageProcessor:
    """Inspects an original image and builds its WebP thumbnail. Knows nothing about Django."""

    def __init__(self, thumb_size=(400, 400), thumb_quality=80):
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality

    def process(self, file) -> ProcessedImage:
        file.seek(0)
        with Image.open(file) as src:
            if src.format not in SUPPORTED_FORMATS:
                raise UnsupportedImageFormat(f'{src.format} is not supported')
            extension = SUPPORTED_FORMATS[src.format]
            img = ImageOps.exif_transpose(src)
        file.seek(0)
        width, height = img.size
        img.thumbnail(self.thumb_size)
        return ProcessedImage(extension, width, height, self._webp(img))

    def _webp(self, img: Image.Image) -> bytes:
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA' if img.has_transparency_data else 'RGB')
        buf = BytesIO()
        img.save(buf, 'WEBP', quality=self.thumb_quality)
        return buf.getvalue()
