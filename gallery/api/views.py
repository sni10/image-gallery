import re
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from PIL import UnidentifiedImageError
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Category, Gallery, Photo
from ..services import CategoryQueries, FavoriteService, GalleryQueries, PhotoQueries, PhotoService
from ..services.signed_media import is_valid
from .pagination import PageLimitPagination
from .permissions import HasIngestKey
from .serializers import (
    CategoryWithCountSerializer, GallerySerializer, PhotoDetailSerializer, PhotoIngestResultSerializer,
    PhotoIngestSerializer, PhotoSerializer,
)

SEED_RE = re.compile(r'^[A-Za-z0-9]{1,32}$')

BAD_PARAMS = OpenApiResponse(description='page или limit не целое число или меньше 1, например {"page": "must be >= 1"}')
NOT_FOUND = OpenApiResponse(description='Галереи с таким id нет (в том числе старый id после перевыпуска ссылки)')
GALLERY_ID = OpenApiParameter('id', str, OpenApiParameter.PATH, description='Публичный id галереи (поле id), не число')
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
    parameters=[OpenApiParameter(
        'category', str, required=False,
        description='slug категории из GET /categories: только её галереи. Неизвестный slug — пустой список.',
    )],
    responses={200: GallerySerializer(many=True), 400: BAD_PARAMS},
)
class GalleryListView(ListAPIView):
    serializer_class = GallerySerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        galleries = GalleryQueries.with_stats()
        category = self.request.query_params.get('category')
        return galleries.filter(category__slug=category) if category else galleries

    def paginate_queryset(self, queryset):
        return GalleryQueries.attach_covers(super().paginate_queryset(queryset), self.request.user)


@extend_schema(summary='Галерея', parameters=[GALLERY_ID], responses={200: GallerySerializer, 404: NOT_FOUND})
class GalleryDetailView(RetrieveAPIView):
    serializer_class = GallerySerializer
    lookup_field = 'public_id'
    lookup_url_kwarg = 'id'

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def get_object(self):
        return GalleryQueries.attach_covers([super().get_object()], self.request.user)[0]


@extend_schema(
    summary='Фото всех галерей в случайном порядке',
    description='Для главной. Порядок задаёт seed: с одним seed все страницы идут в одном порядке, '
                'фото не повторяются и не пропадают. Новый seed — новый порядок. '
                'Гость: открыты первые 10 позиций ленты, и только из фото, открытых в своих галереях '
                '(они идут первыми); остальные locked.',
    parameters=[OpenApiParameter(
        'seed', str, required=True, pattern=SEED_RE.pattern,
        description='Ключ случайного порядка: 1–32 латинских буквы или цифры. Сгенерируйте при заходе на страницу '
                    'и передавайте во всех запросах подгрузки.',
    )],
    responses={200: PhotoSerializer(many=True), 400: OpenApiResponse(description='Нет seed или неверный page/limit/seed')},
)
class RandomPhotoListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        seed = self.request.query_params.get('seed', '')
        if not SEED_RE.fullmatch(seed):
            raise ValidationError({'seed': 'required, 1-32 latin letters or digits'})
        user, photos = self.request.user, PhotoQueries.shuffled(seed)
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


UNAUTHORIZED = OpenApiResponse(description='Нет действующего access-токена')


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

    @extend_schema(
        summary='Фото',
        description='Для страницы фото: фото, его галерея и категория.',
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
