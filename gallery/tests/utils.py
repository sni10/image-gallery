from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from ..models import Category, Gallery


def image(w, h, name='p.jpg', fmt='JPEG', mode='RGB', **save_kwargs):
    buf = BytesIO()
    Image.new(mode, (w, h)).save(buf, fmt, **save_kwargs)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f'image/{fmt.lower()}')


def jpeg(w, h, name='p.jpg'):
    return image(w, h, name)


def make_category(slug='test', title=None, position=0):
    return Category.objects.get_or_create(slug=slug, defaults={'title': title or slug.title(), 'position': position})[0]


def gallery(title='Test', category=None):
    return Gallery.objects.create(title=title, category=category or make_category())
