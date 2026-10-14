import re
from urllib.parse import urlsplit

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Category, Collection, Gallery, Photo
from ..services import PhotoQueries
from ..services.signed_media import signed_query


class GalleryRefSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')

    class Meta:
        model = Gallery
        fields = ['id', 'title']


class PhotoSerializer(serializers.ModelSerializer):
    id =serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')
    url = serializers.SerializerMethodField(
        help_text='Оригинал со знаком (jpg/png/webp/gif/avif), подписанная ссылка с ограниченным сроком (exp, sig). '
                  'null, если фото закрыто (locked). Для лайтбокса и зума 1:1',
    )
    thumbUrl = serializers.SerializerMethodField(
        method_name='get_thumb_url', help_text='Превью WebP, не больше 400px по длинной стороне, абсолютная ссылка, '
                                               'без срока. null только у закрытого фото без превью',
    )
    locked = serializers.SerializerMethodField(
        help_text='Фото закрыто для гостя: url = null, показывать превью и предлагать вход. '
                  'Гостю открыты 10 новых фото каждой галереи, в общей ленте GET /photos закрыты все. С токеном всегда false',
    )
    isFavorite = serializers.BooleanField(
        source='is_favorite', read_only=True, help_text='В избранном у текущего пользователя; для анонима всегда false',
    )
    gallery = GalleryRefSerializer(
        read_only=True, help_text='Галерея фото: id и название, для ссылки "открыть галерею" в сетке',
    )

    class Meta:
        model = Photo
        fields = ['id', 'title', 'description', 'tags', 'url', 'thumbUrl', 'width', 'height', 'isFavorite', 'locked',
                  'gallery']
        extra_kwargs = {
            'title': {'help_text': 'Название; если не задано — имя загруженного файла'},
            'description': {'help_text': 'Описание, может быть пустым'},
            'tags': {'help_text': 'Теги в нижнем регистре, без #; может быть пустым списком'},
            'width': {'help_text': 'Ширина оригинала в px с учётом поворота по EXIF'},
            'height': {'help_text': 'Высота оригинала в px с учётом поворота по EXIF'},
        }

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_locked(self, obj):
        locked = getattr(obj, 'locked', None)  # from PhotoQueries.with_locked
        return locked if locked is not None else not self.context['request'].user.is_authenticated  # fail closed

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_url(self, obj):
        return None if self.get_locked(obj) else self._signed(obj.image)

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumb_url(self, obj):
        if obj.thumb:
            return self.context['request'].build_absolute_uri(obj.thumb.url)
        return None if self.get_locked(obj) else self._signed(obj.image)  # never the original of a locked photo

    def _signed(self, file):
        url = file.url
        return self.context['request'].build_absolute_uri(f'{url}?{signed_query(urlsplit(url).path)}')


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


class PhotoGallerySerializer(GalleryRefSerializer):
    category = CategorySerializer(read_only=True, help_text='Категория галереи, всегда заполнена')

    class Meta(GalleryRefSerializer.Meta):
        fields = [*GalleryRefSerializer.Meta.fields, 'category']


class PhotoDetailSerializer(PhotoSerializer):
    gallery = PhotoGallerySerializer(read_only=True, help_text='Галерея фото и её категория, для хлебных крошек')
    prevId = serializers.SerializerMethodField(
        help_text='Id фото перед текущим в списке галереи (более новое); null, если текущее первое',
    )
    nextId = serializers.SerializerMethodField(
        help_text='Id фото после текущего в списке галереи (более старое); null, если текущее последнее',
    )

    class Meta(PhotoSerializer.Meta):
        fields = [*PhotoSerializer.Meta.fields, 'prevId', 'nextId']  # `gallery` overridden above, with category

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_prevId(self, obj):
        return self._neighbors(obj)[0]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_nextId(self, obj):
        return self._neighbors(obj)[1]

    @staticmethod
    def _neighbors(obj):  # both fields from one pair of queries
        if not hasattr(obj, '_neighbors'):
            obj._neighbors = PhotoQueries.neighbors(obj)
        return obj._neighbors


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


class ComplaintSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254, help_text='Куда ответить')
    photoUrl = serializers.URLField(max_length=500, required=False, allow_blank=True, default='',
                                    help_text='Ссылка на фото, необязательно')
    message = serializers.CharField(min_length=10, max_length=5000, help_text='10–5000 символов')


class CollectionSerializer(serializers.ModelSerializer):
    """Expects collections from CollectionQueries.of_user()."""

    id = serializers.CharField(source='public_id', read_only=True, help_text='Публичный id: 26 символов [a-z2-7], не число')
    title = serializers.CharField(max_length=100, help_text='1–100 символов, пробелы по краям обрезаются')
    photosCount = serializers.IntegerField(source='photos_count', read_only=True, help_text='Сколько фото в коллекции')

    class Meta:
        model = Collection
        fields = ['id', 'title', 'photosCount']


class CollectionWithCoverSerializer(CollectionSerializer):
    """Expects covers from CollectionQueries.attach_covers()."""

    cover = PhotoSerializer(read_only=True, allow_null=True, help_text='Последнее добавленное фото; null, если пусто')
    hasPhoto = serializers.BooleanField(
        source='has_photo', required=False,  # not read_only: OpenAPI marks read-only fields required
        help_text='Только при ?photo=<id>: есть ли это фото в коллекции',
    )

    class Meta(CollectionSerializer.Meta):
        fields = [*CollectionSerializer.Meta.fields, 'cover', 'hasPhoto']


class FeedFiltersSerializer(serializers.Serializer):
    """Query params of GET /photos that narrow the feed."""

    tag = serializers.CharField(required=False, help_text='Только фото с этим тегом. Регистр, # и пробелы по краям не важны')
    q = serializers.CharField(required=False, min_length=2, max_length=100,
                              help_text='Поиск: часть тега, описания, названия фото, галереи или категории; 2–100 символов')

    def validate_tag(self, value):
        return clean_tag(value)


def clean_tag(value: str) -> str:
    """A tag from a query string: case, a leading # and outer spaces don't matter."""
    tag = value.lstrip('#').strip().lower()
    if not tag or len(tag) > MAX_TAG_LENGTH:
        raise serializers.ValidationError(f'Must be 1-{MAX_TAG_LENGTH} characters.')
    return tag


class TagsQuerySerializer(serializers.Serializer):
    related = serializers.CharField(required=False, help_text='Тег: отдать теги, которые стоят на одних фото с ним. '
                                                              'Регистр, # и пробелы по краям не важны')
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20, help_text='1–50')

    def validate_related(self, value):
        return clean_tag(value)


class TagCountSerializer(serializers.Serializer):
    tag = serializers.CharField()
    count = serializers.IntegerField(help_text='С related — число общих фото с этим тегом, без — число фото с тегом')
