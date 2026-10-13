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


def photo(gallery, tags=(), name='original/p.jpg'):
    """A row without files (fast); the serializer builds links from the name. Use with a temporary MEDIA_ROOT."""
    from ..models import Photo
    return Photo.objects.create(gallery=gallery, image=name, tags=list(tags))


def bearer(user):
    from accounts.services.access_tokens import AccessTokenService
    return {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(user)}'}
