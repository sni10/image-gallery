import re

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Category, Gallery, Photo


class PhotoSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')
    url = serializers.SerializerMethodField(
        help_text='Оригинал без метаданных (jpg/png/webp/gif/avif), абсолютная ссылка. Для лайтбокса и зума 1:1',
    )
    thumbUrl = serializers.SerializerMethodField(
        method_name='get_thumb_url', help_text='Превью WebP, не больше 400px по длинной стороне, абсолютная ссылка',
    )
    isFavorite = serializers.BooleanField(
        source='is_favorite', read_only=True, help_text='В избранном у текущего пользователя; для анонима всегда false',
    )

    class Meta:
        model = Photo
        fields = ['id', 'title', 'description', 'tags', 'url', 'thumbUrl', 'width', 'height', 'isFavorite']
        extra_kwargs = {
            'title': {'help_text': 'Название; если не задано — имя загруженного файла'},
            'description': {'help_text': 'Описание, может быть пустым'},
            'tags': {'help_text': 'Теги в нижнем регистре, без #; может быть пустым списком'},
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


class PhotoGallerySerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')
    category = CategorySerializer(read_only=True, help_text='Категория галереи, всегда заполнена')

    class Meta:
        model = Gallery
        fields = ['id', 'title', 'category']


class PhotoDetailSerializer(PhotoSerializer):
    gallery = PhotoGallerySerializer(read_only=True, help_text='Галерея фото и её категория, для хлебных крошек')

    class Meta(PhotoSerializer.Meta):
        fields = [*PhotoSerializer.Meta.fields, 'gallery']


TAG_SEPARATORS = re.compile(r'[,\n]')
MAX_TAGS, MAX_TAG_LENGTH = 30, 50


class PhotoIngestSerializer(serializers.Serializer):
    """Input of POST /ingest/photos. Choose the gallery by `gallery` or by `category` + `galleryTitle`."""

    image = serializers.FileField(help_text='JPEG/PNG/WebP/GIF/AVIF. Метаданные (EXIF, XMP, текст PNG) сервер удаляет')
    gallery = serializers.CharField(required=False, help_text='Публичный id существующей галереи')
    category = serializers.SlugField(required=False, help_text='slug категории — вместе с galleryTitle')
    galleryTitle = serializers.CharField(
        required=False, max_length=200, help_text='Название галереи в category: найдётся по точному названию или создастся',
    )
    title = serializers.CharField(required=False, allow_blank=True, max_length=200, default='',
                                  help_text='Если пусто — имя файла')
    description = serializers.CharField(required=False, allow_blank=True, max_length=5000, default='')
    tags = serializers.CharField(
        required=False, allow_blank=True, default='',
        help_text=f'Через запятую или с новой строки: "cat, #Neon". Приводятся к нижнему регистру, без # и дублей; '
                  f'не больше {MAX_TAGS} тегов по {MAX_TAG_LENGTH} символов',
    )

    def validate_tags(self, value):
        tags = list(dict.fromkeys(t.strip().lstrip('#').strip().lower() for t in TAG_SEPARATORS.split(value)))
        tags = [t for t in tags if t]
        if too_long := [t for t in tags if len(t) > MAX_TAG_LENGTH]:
            raise serializers.ValidationError(f'Tags longer than {MAX_TAG_LENGTH} chars: {", ".join(too_long)}')
        if len(tags) > MAX_TAGS:
            raise serializers.ValidationError(f'At most {MAX_TAGS} tags, got {len(tags)}')
        return tags

    def validate(self, attrs):
        by_id = 'gallery' in attrs
        by_title = 'category' in attrs or 'galleryTitle' in attrs
        if by_id == by_title:
            raise serializers.ValidationError({'gallery': 'Give either gallery or category + galleryTitle'})
        if by_title and not ('category' in attrs and 'galleryTitle' in attrs):
            missing = 'galleryTitle' if 'category' in attrs else 'category'
            raise serializers.ValidationError({missing: 'Required together with ' + ({'category', 'galleryTitle'} - {missing}).pop()})
        return attrs


class IngestGallerySerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id', read_only=True)
    category = serializers.CharField(source='category.slug', read_only=True)

    class Meta:
        model = Gallery
        fields = ['id', 'title', 'category']


class PhotoIngestResultSerializer(serializers.Serializer):
    photo = PhotoSerializer()
    gallery = IngestGallerySerializer(source='photo.gallery')
