from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Category, Gallery, Photo


class PhotoSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')
    url = serializers.SerializerMethodField(
        help_text='Оригинал без изменений (jpg/png/webp/gif/avif), абсолютная ссылка. Для лайтбокса и зума 1:1',
    )
    thumbUrl = serializers.SerializerMethodField(
        method_name='get_thumb_url', help_text='Превью WebP, не больше 400px по длинной стороне, абсолютная ссылка',
    )
    isFavorite = serializers.BooleanField(
        source='is_favorite', read_only=True, help_text='В избранном у текущего пользователя; для анонима всегда false',
    )

    class Meta:
        model = Photo
        fields = ['id', 'title', 'url', 'thumbUrl', 'width', 'height', 'isFavorite']
        extra_kwargs = {
            'title': {'help_text': 'Название; если не задано — имя загруженного файла'},
            'width': {'help_text': 'Ширина оригинала в px с учётом поворота по EXIF'},
            'height': {'help_text': 'Высота оригинала в px с учётом поворота по EXIF'},
        }

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, obj):
        return self._absolute(obj.image)

    @extend_schema_field(OpenApiTypes.URI)
    def get_thumb_url(self, obj):
        return self._absolute(obj.thumb or obj.image)

    def _absolute(self, file):
        return self.context['request'].build_absolute_uri(file.url)


class CategorySerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')

    class Meta:
        model = Category
        fields = ['id', 'slug', 'title']
        extra_kwargs = {'slug': {'help_text': 'Для адреса и фильтра GET /galleries?category=<slug>'}}


class CategoryWithCountSerializer(CategorySerializer):
    galleriesCount = serializers.IntegerField(source='galleries_count', read_only=True,
                                              help_text='Сколько галерей в категории, всегда больше 0')

    class Meta(CategorySerializer.Meta):
        fields = [*CategorySerializer.Meta.fields, 'galleriesCount']


class GallerySerializer(serializers.ModelSerializer):
    """Expects galleries from GalleryQueries.with_stats() with covers attached."""

    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')
    photosCount = serializers.IntegerField(source='photos_count', read_only=True, help_text='Сколько фото в галерее')
    category = CategorySerializer(read_only=True, help_text='Категория галереи, всегда заполнена')
    cover = PhotoSerializer(
        source='display_cover', read_only=True, allow_null=True,
        help_text='Выбранная обложка, иначе случайное фото галереи; null, если фото нет',
    )

    class Meta:
        model = Gallery
        fields = ['id', 'title', 'category', 'photosCount', 'cover']
