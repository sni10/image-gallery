from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models

from common.models import PublicIdModel


class Category(PublicIdModel):
    """Section of the catalog (AI, comics, ...). Every gallery belongs to exactly one category."""

    title = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, help_text='Для адреса: латиница, цифры, дефис (например ai, comics)')
    position = models.IntegerField(default=0, help_text='Порядок в списке категорий: меньше — выше')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'title']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.title

    def clean(self):
        self.slug = self.slug.lower()  # SlugField accepts upper case; addresses are lower case


class Gallery(PublicIdModel):
    title = models.CharField(max_length=200)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='galleries', verbose_name='Категория',
    )
    cover = models.ForeignKey(
        'Photo', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Обложка', help_text='Если не выбрана — случайное фото галереи при каждом запросе',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name_plural = 'galleries'

    def __str__(self):
        return self.title

    def clean(self):
        if self.cover_id and self.cover.gallery_id != self.pk:
            raise ValidationError({'cover': 'Обложка должна быть фото из этой галереи'})


class Photo(PublicIdModel):
    """Stored photo. Files are prepared by PhotoService, the model only holds data."""

    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='photos')
    title = models.CharField(max_length=200, blank=True, help_text='Если пусто — имя файла')
    description = models.TextField(blank=True, default='')
    # ponytail: a Tag model + GIN index once there are tag pages / tag search; tags__contains=['cat'] works now
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True, help_text='Нижний регистр, без #')
    image = models.ImageField(upload_to='original/', help_text='Оригинал без метаданных (EXIF, XMP, текст PNG)')
    thumb = models.ImageField(upload_to='thumb/', blank=True, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.title


class Favorite(models.Model):
    """A photo in a user's favorites. Deleting the photo or the user deletes the record."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'photo'], name='unique_favorite_per_user')]
        indexes = [models.Index(fields=['user', '-created_at'], name='favorite_user_recent')]


class Complaint(models.Model):
    """A complaint about content from the /complaint form. Kept even if the email to the admin was not sent."""

    email = models.EmailField(help_text='Сюда отвечать')
    photo_url = models.CharField(max_length=500, blank=True)
    message = models.TextField()
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField('Обработана', default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email}: {self.photo_url or "без ссылки"}'


class Collection(PublicIdModel):
    """A user's private folder of photos (like a board). Separate from favorites."""

    MAX_PER_USER = 100
    MAX_PHOTOS = 1000

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collections')
    title = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, help_text='Также при добавлении и удалении фото')

    class Meta:
        indexes = [models.Index(fields=['user', '-updated_at'], name='collection_user_recent')]

    def __str__(self):
        return self.title


class CollectionPhoto(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='links')
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name='collection_links')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['collection', 'photo'], name='unique_photo_per_collection')]
