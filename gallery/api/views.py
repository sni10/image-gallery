import re
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from PIL import UnidentifiedImageError
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Category, Gallery, Photo
from ..services import CategoryQueries, FavoriteService, GalleryQueries, PhotoQueries, PhotoService
from ..services.recommendations import photos_in_order, similar_ids, wave_ids
from ..services.signed_media import is_valid
from .pagination import PageLimitPagination
from .permissions import HasIngestKey
from .serializers import (
    CategoryWithCountSerializer, FeedFiltersSerializer, GalleryCoverSerializer, GallerySerializer,
    PhotoDetailSerializer, PhotoIngestResultSerializer, PhotoIngestSerializer, PhotoSerializer, TagCountSerializer,
    TagsQuerySerializer, WaveSerializer,
)

SEED_RE = re.compile(r'^[A-Za-z0-9]{1,32}$')
FEED_SORTS = {'random': None, 'new': PhotoQueries.newest, 'popular': PhotoQueries.popular}  # random needs the seed
SIMILAR_LIMIT, SIMILAR_MAX = 12, 24
GALLERY_Q_MAX = 100

BAD_PARAMS = OpenApiResponse(description='page или limit не целое число или меньше 1, например {"page": "must be >= 1"}')
NOT_FOUND = OpenApiResponse(description='Галереи с таким id нет (в том числе старый id после перевыпуска ссылки)')
GALLERY_ID = OpenApiParameter('id', str, OpenApiParameter.PATH, description='Публичный id галереи (поле id), не число')
UNAUTHORIZED = OpenApiResponse(description='Нет действующего access-токена')
PHOTO_ID = OpenApiParameter('photo_id', str, OpenApiParameter.PATH, description='Публичный id фото (поле id), не число')


@extend_schema(
    summary='Категории',
    description='Только категории, где есть хотя бы одна галерея, в порядке, заданном в админке. Без пагинации.',
    responses={200: CategoryWithCountSerializer(many=True)},
)
class CategoryListView(ListAPIView):
    serializer_class = CategoryWithCountSerializer
    pagination_class = None

    def get_queryset(self):
        return CategoryQueries.non_empty()


@extend_schema(
    summary='Каталог галерей',
    description='Сначала новые. Обложка — выбранная в админке, иначе случайное фото галереи (новое при каждом запросе).',
    parameters=[
        OpenApiParameter(
            'category', str, required=False,
            description='slug категории из GET /categories: только её галереи. Неизвестный slug — пустой список.',
        ),
        OpenApiParameter(
            'q', str, required=False,
            description=f'Часть названия галереи, без учёта регистра; вместе с category — через И. Пробелы по краям '
                        f'обрезаются, пустой q — без фильтра. До {GALLERY_Q_MAX} символов.',
        ),
    ],
    responses={200: GallerySerializer(many=True),
               400: OpenApiResponse(description=f'Неверный page/limit или q длиннее {GALLERY_Q_MAX} символов, '
                                                'например {"q": ["..."]}')},
)
class GalleryListView(ListAPIView):
    serializer_class = GallerySerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        galleries = GalleryQueries.with_stats()
        category = self.request.query_params.get('category')
        if category:
            galleries = galleries.filter(category__slug=category)
        q = self.request.query_params.get('q', '').strip()
        if len(q) > GALLERY_Q_MAX:
            raise ValidationError({'q': [f'Ensure this field has no more than {GALLERY_Q_MAX} characters.']})
        # ponytail: plain icontains, fine for thousands of galleries; trigram GIN index on title if it gets slow
        return galleries.filter(title__icontains=q) if q else galleries

    def paginate_queryset(self, queryset):
        return GalleryQueries.attach_covers(super().paginate_queryset(queryset), self.request.user)


@extend_schema(summary='Галерея', parameters=[GALLERY_ID], responses={200: GallerySerializer, 404: NOT_FOUND})
class GalleryDetailView(RetrieveAPIView):
    serializer_class = GallerySerializer
    lookup_field = 'public_id'
    lookup_url_kwarg = 'id'

    def get_permissions(self):  # reading is public, choosing the cover is for admins
        return [IsAdminUser()] if self.request.method == 'PATCH' else super().get_permissions()

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def get_object(self):
        return GalleryQueries.attach_covers([super().get_object()], self.request.user)[0]

    @extend_schema(
        summary='Поставить или снять обложку галереи',
        description='Только для is_staff. Другие поля галереи не меняются, лишние ключи в теле игнорируются. '
                    'Ответ — галерея целиком, как GET /galleries/{id}.',
        request=GalleryCoverSerializer,
        responses={200: GallerySerializer, 400: OpenApiResponse(description='Фото не из этой галереи или нет такого '
                                                                            'фото: {"cover": ["..."]}'),
                   401: UNAUTHORIZED, 403: OpenApiResponse(description='Пользователь не админ'), 404: NOT_FOUND},
    )
    def patch(self, request, id):
        gallery = get_object_or_404(Gallery, public_id=id)
        data = GalleryCoverSerializer(data=request.data, context={'gallery': gallery})
        data.is_valid(raise_exception=True)
        gallery.cover = data.validated_data['cover']
        gallery.save(update_fields=['cover'])
        return Response(self.get_serializer(self.get_object()).data)


@extend_schema(
    summary='Лента главной: фото всех галерей',
    description='Порядок — sort. random: порядок задаёт seed, с одним seed все страницы идут в одном порядке, '
                'фото не повторяются и не пропадают; новый seed — новый порядок. new: сначала новые. '
                'popular: сначала чаще добавляемые в избранное (само число не отдаётся). '
                'Гость: открыты первые 10 позиций ленты, и только из фото, открытых в своих галереях '
                '(они идут первыми, в порядке sort); остальные locked.',
    parameters=[
        OpenApiParameter('sort', str, required=False, enum=list(FEED_SORTS), default='random',
                         description='Порядок ленты'),
        OpenApiParameter(
            'seed', str, required=False, pattern=SEED_RE.pattern,
            description='Обязателен при sort=random, иначе игнорируется. Ключ случайного порядка: 1–32 латинских '
                        'буквы или цифры. Сгенерируйте при заходе на страницу и передавайте во всех запросах подгрузки.',
        ),
        FeedFiltersSerializer,
    ],
    responses={200: PhotoSerializer(many=True),
               400: OpenApiResponse(description='Неизвестный sort, нет seed при random, неверный page/limit/seed/tag/q, '
                                                'например {"q": ["Ensure this field has at least 2 characters."]}')},
)
class RandomPhotoListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        filters = FeedFiltersSerializer(data=self.request.query_params.dict())  # a QueryDict treats tag= as absent
        filters.is_valid(raise_exception=True)
        sort = self.request.query_params.get('sort', 'random')
        if sort not in FEED_SORTS:
            raise ValidationError({'sort': [f'must be one of: {", ".join(FEED_SORTS)}']})
        if sort == 'random':
            seed = self.request.query_params.get('seed', '')
            if not SEED_RE.fullmatch(seed):
                raise ValidationError({'seed': 'required, 1-32 latin letters or digits'})
            photos = PhotoQueries.shuffled(seed)
        else:
            photos = FEED_SORTS[sort]()
        if 'tag' in filters.validated_data:
            photos = photos.filter(tags__contains=[filters.validated_data['tag']])
        if 'q' in filters.validated_data:
            photos = PhotoQueries.search(photos, filters.validated_data['q'])
        user = self.request.user
        if user.is_authenticated:
            return PhotoQueries.for_user(photos, user)
        return PhotoQueries.with_is_favorite(PhotoQueries.guest_feed(photos), user)

    def paginate_queryset(self, queryset):
        photos = super().paginate_queryset(queryset)
        if not self.request.user.is_authenticated:  # guest: only the first positions of the whole feed are open
            start = self.paginator.offset
            for i, photo in enumerate(photos):
                photo.locked = not (photo.guest_free and start + i < settings.GUEST_FREE_PHOTOS)
        return photos


@extend_schema(
    summary='Фото галереи',
    description='Сначала новые. 404 проверяется раньше параметров пагинации.',
    parameters=[GALLERY_ID],
    responses={200: PhotoSerializer(many=True), 400: BAD_PARAMS, 404: NOT_FOUND},
)
class GalleryPhotoListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real request
            return Photo.objects.none()
        photos = get_object_or_404(Gallery, public_id=self.kwargs['id']).photos.all()
        return PhotoQueries.for_user(photos, self.request.user)



@extend_schema(
    summary='Избранное текущего пользователя',
    description='Сначала недавно добавленные. Пагинация как у остальных списков.',
    responses={200: PhotoSerializer(many=True), 400: BAD_PARAMS, 401: UNAUTHORIZED},
)
class FavoriteListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return Photo.objects.none()
        return PhotoQueries.for_user(PhotoQueries.favorites_of(self.request.user), self.request.user)


class FavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Добавить фото в избранное', request=None, parameters=[PHOTO_ID],
        responses={204: OpenApiResponse(description='Добавлено (или уже было)'), 401: UNAUTHORIZED,
                   404: OpenApiResponse(description='Фото с таким id нет')},
    )
    def put(self, request, photo_id):
        try:
            FavoriteService.add(request.user, photo_id)
        except Photo.DoesNotExist:
            raise NotFound('Photo not found.')
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Убрать фото из избранного', parameters=[PHOTO_ID],
        responses={204: OpenApiResponse(description='Убрано (или его и не было)'), 401: UNAUTHORIZED},
    )
    def delete(self, request, photo_id):
        FavoriteService.remove(request.user, photo_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PhotoDetailView(RetrieveAPIView):
    serializer_class = PhotoDetailSerializer
    lookup_field = 'public_id'
    lookup_url_kwarg = 'photo_id'

    def get_permissions(self):  # reading is public, deleting is for admins
        return [IsAdminUser()] if self.request.method == 'DELETE' else super().get_permissions()

    def get_queryset(self):
        photos = Photo.objects.select_related('gallery__category')
        return PhotoQueries.for_user(photos, self.request.user)

    def get_object(self):
        photo = super().get_object()
        if HasIngestKey().has_permission(self.request, self):  # custom/seo.py feeds originals to its LLM
            photo.locked = False
        return photo

    @extend_schema(
        summary='Фото',
        description='Для страницы фото: фото, его галерея и категория. С `X-Api-Key` (INGEST_API_KEY) фото '
                    'всегда открыто: url есть и у закрытых для гостя.',
        parameters=[PHOTO_ID],
        responses={200: PhotoDetailSerializer,
                   404: OpenApiResponse(description='Фото с таким id нет (в том числе старый id после перевыпуска)')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary='Удалить фото насовсем (админ)',
        description='Только для is_staff, без восстановления. Файлы удаляются, если на них не ссылаются другие фото; '
                    'обложка галереи сбрасывается на случайное фото; фото пропадает из избранного.',
        parameters=[PHOTO_ID],
        responses={204: OpenApiResponse(description='Удалено'), 401: UNAUTHORIZED,
                   403: OpenApiResponse(description='Пользователь не админ'),
                   404: OpenApiResponse(description='Фото с таким id нет: уже удалено или id перевыпущен')},
    )
    def delete(self, request, photo_id):
        if not PhotoService.delete(Photo.objects.filter(public_id=photo_id)):
            raise NotFound('Photo not found.')
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    summary='Похожие фото',
    description='Бесконечная лента «похожие» на странице фото. Порядок и подбор — забота сервера '
                '(по вектору картинки и общим тегам, не больше 3 фото одной галереи на каждые 24 места; у фото '
                'без вектора — по тегам); само фото в список не входит. Порядок одинаков от запроса к запросу: '
                'страницы не пересекаются. Пустой items — конец ленты, total не отдаётся.',
    parameters=[PHOTO_ID, OpenApiParameter('limit', int, required=False, default=SIMILAR_LIMIT,
                                           description=f'Сколько фото, 1–{SIMILAR_MAX}'),
                OpenApiParameter('page', int, required=False, default=1, description='Номер страницы, с 1')],
    responses={
        200: inline_serializer('SimilarPhotos', {'items': PhotoSerializer(many=True)}),
        400: OpenApiResponse(description='limit не целое число от 1 до 24 или page не целое число от 1'),
        404: OpenApiResponse(description='Фото с таким id нет'),
    },
)
class SimilarPhotoListView(APIView):
    def get(self, request, photo_id):
        try:
            limit = int(request.query_params.get('limit', SIMILAR_LIMIT))
        except ValueError:
            limit = 0
        if not 1 <= limit <= SIMILAR_MAX:
            raise ValidationError({'limit': [f'must be an integer from 1 to {SIMILAR_MAX}']})
        try:
            page = int(request.query_params.get('page', 1))
        except ValueError:
            page = 0
        if page < 1:
            raise ValidationError({'page': ['must be an integer from 1']})
        photo = get_object_or_404(Photo.objects.select_related('gallery'), public_id=photo_id)
        photos = photos_in_order(similar_ids(photo, limit, page), request.user)
        return Response({'items': PhotoSerializer(photos, many=True, context={'request': request}).data})


@extend_schema(
    summary='Моя волна',
    description='Бесконечная лента рекомендаций по избранному. Сервер ничего не хранит: id показанных фото фронт '
                'передаёт в exclude. Избранное в ленту не попадает; лайк — обычный PUT /me/favorites/{id}. '
                'Пустой список — показывать больше нечего.',
    request=WaveSerializer,
    responses={
        200: inline_serializer('WavePhotos', {'items': PhotoSerializer(many=True)}),
        400: OpenApiResponse(description='exclude длиннее 2000 или limit не от 1 до 48, например {"limit": ["..."]}'),
        401: UNAUTHORIZED,
    },
)
class WaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        params = WaveSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        ids = wave_ids(request.user, params.validated_data['exclude'], params.validated_data['limit'])
        photos = photos_in_order(ids, request.user)
        return Response({'items': PhotoSerializer(photos, many=True, context={'request': request}).data})


@extend_schema(
    summary='Теги: самые частые или связанные с тегом',
    description='Для строки тегов на странице тега. Без авторизации, без пагинации. Порядок: count по убыванию, '
                'при равенстве по имени. Неизвестный тег — пустой список.',
    parameters=[TagsQuerySerializer],
    responses={200: inline_serializer('TagList', {'items': TagCountSerializer(many=True)}),
               400: OpenApiResponse(description='limit не от 1 до 50 или пустой related, например {"limit": ["..."]}')},
)
class TagListView(APIView):
    def get(self, request):
        params = TagsQuerySerializer(data=request.query_params.dict())  # a QueryDict treats related= as absent
        params.is_valid(raise_exception=True)
        rows = PhotoQueries.tag_counts(params.validated_data['limit'], params.validated_data.get('related'))
        return Response({'items': [{'tag': tag, 'count': count} for tag, count in rows]})


@extend_schema(
    summary='Загрузить фото (автоматизация)',
    description='Для скриптов и ComfyUI. Авторизация — заголовок `X-Api-Key` (INGEST_API_KEY на сервере), не Bearer. '
                'Галерея — по `gallery` или по `category` + `galleryTitle` (нет такой — создаётся). '
                'Метаданные оригинала (EXIF, XMP, текст PNG) удаляются. Повтор той же картинки в ту же галерею '
                'не создаёт дубль: 200 и уже существующее фото, присланные title/description/tags не применяются.',
    request={'multipart/form-data': PhotoIngestSerializer},
    responses={
        201: PhotoIngestResultSerializer,
        200: OpenApiResponse(PhotoIngestResultSerializer, description='Такая картинка уже есть в этой галерее'),
        400: OpenApiResponse(description='Ошибки по полям, например {"image": ["..."]} или {"tags": ["..."]}'),
        403: OpenApiResponse(description='Нет или неверный X-Api-Key, либо загрузка выключена на сервере'),
        404: OpenApiResponse(description='Галереи с таким id или категории с таким slug нет'),
    },
    auth=[],
)
class PhotoIngestView(APIView):
    authentication_classes = []  # a stray Bearer header must not turn into a 401
    permission_classes = [HasIngestKey]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        data = PhotoIngestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        fields = data.validated_data
        gallery = self._gallery(fields)
        try:
            photo, created = PhotoService().get_or_create(
                fields['image'], gallery, fields['title'], fields['description'], fields['tags'],
            )
        except (ValueError, UnidentifiedImageError) as exc:  # unsupported or broken image
            raise ValidationError({'image': [str(exc) or 'Not a supported image']})
        photo.is_favorite, photo.locked = False, False  # PhotoSerializer reads the annotations; the key opens everything
        body = PhotoIngestResultSerializer({'photo': photo}, context={'request': request}).data
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @staticmethod
    def _gallery(fields) -> Gallery:
        if 'gallery' in fields:
            return get_object_or_404(Gallery.objects.select_related('category'), public_id=fields['gallery'])
        category = get_object_or_404(Category, slug=fields['category'])
        # ponytail: no unique (category, title); parallel first uploads could create two galleries. ComfyUI sends
        # one at a time; add a UniqueConstraint if that changes
        gallery = category.galleries.filter(title=fields['galleryTitle']).order_by('id').first()
        return gallery or Gallery.objects.create(category=category, title=fields['galleryTitle'])


def media_auth(request):
    """Caddy forward_auth target for /media/original/*: 204 if the link's signature is valid and not expired, else 403.
    Caddy passes the original request URI in X-Forwarded-Uri. No DB, no DRF: it runs on every image request.
    Reachable only from Caddy inside the stack: /internal/* answers 404 on every public host."""
    uri = urlsplit(request.headers.get('X-Forwarded-Uri', ''))
    query = parse_qs(uri.query)
    exp, sig = (query.get(key, [None])[-1] for key in ('exp', 'sig'))
    return HttpResponse(status=204 if is_valid(uri.path, exp, sig) else 403)
