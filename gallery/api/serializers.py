from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Gallery, Photo


class PhotoSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True, help_text='Числовой id в виде строки')
    url = serializers.SerializerMethodField(
        help_text='Оригинал без изменений (jpg/png/webp/gif/avif), абсолютная ссылка. Для лайтбокса и зума 1:1',
    )
    thumbUrl = serializers.SerializerMethodField(
        method_name='get_thumb_url', help_text='Превью WebP, не больше 400px по длинной стороне, абсолютная ссылка',
    )

    class Meta:
        model = Photo
        fields = ['id', 'title', 'url', 'thumbUrl', 'width', 'height']
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


class GallerySerializer(serializers.ModelSerializer):
    """Expects galleries from GalleryQueries.with_stats() with covers attached."""

    id = serializers.CharField(read_only=True, help_text='Числовой id в виде строки')
    photosCount = serializers.IntegerField(source='photos_count', read_only=True, help_text='Сколько фото в галерее')
    cover = PhotoSerializer(
        source='display_cover', read_only=True, allow_null=True,
        help_text='Выбранная обложка, иначе случайное фото галереи; null, если фото нет',
    )

    class Meta:
        model = Gallery
        fields = ['id', 'title', 'photosCount', 'cover']
