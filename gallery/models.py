from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Category(models.Model):
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


class Gallery(models.Model):
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


class Photo(models.Model):
    """Stored photo. Files are prepared by PhotoService, the model only holds data."""

    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='photos')
    title = models.CharField(max_length=200, blank=True, help_text='Если пусто — имя файла')
    image = models.ImageField(upload_to='original/', help_text='Оригинал, хранится и отдаётся без изменений')
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
