from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from ..models import Gallery


def image(w, h, name='p.jpg', fmt='JPEG', mode='RGB', **save_kwargs):
    buf = BytesIO()
    Image.new(mode, (w, h)).save(buf, fmt, **save_kwargs)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f'image/{fmt.lower()}')


def jpeg(w, h, name='p.jpg'):
    return image(w, h, name)


def gallery(title='Test'):
    return Gallery.objects.create(title=title)
