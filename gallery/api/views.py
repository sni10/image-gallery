import re

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Gallery, Photo
from ..services import FavoriteService, GalleryQueries, PhotoQueries
from .pagination import PageLimitPagination
from .serializers import GallerySerializer, PhotoSerializer

SEED_RE = re.compile(r'^[A-Za-z0-9]{1,32}$')

BAD_PARAMS = OpenApiResponse(description='page или limit не целое число или меньше 1, например {"page": "must be >= 1"}')
NOT_FOUND = OpenApiResponse(description='Галереи с таким id нет')


@extend_schema(
    summary='Каталог галерей',
    description='Сначала новые. Обложка — выбранная в админке, иначе случайное фото галереи (новое при каждом запросе).',
    responses={200: GallerySerializer(many=True), 400: BAD_PARAMS},
)
class GalleryListView(ListAPIView):
    serializer_class = GallerySerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def paginate_queryset(self, queryset):
        return GalleryQueries.attach_covers(super().paginate_queryset(queryset), self.request.user)


@extend_schema(summary='Галерея', responses={200: GallerySerializer, 404: NOT_FOUND})
class GalleryDetailView(RetrieveAPIView):
    serializer_class = GallerySerializer

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def get_object(self):
        return GalleryQueries.attach_covers([super().get_object()], self.request.user)[0]


@extend_schema(
    summary='Фото всех галерей в случайном порядке',
    description='Для главной. Порядок задаёт seed: с одним seed все страницы идут в одном порядке, '
                'фото не повторяются и не пропадают. Новый seed — новый порядок.',
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
        return PhotoQueries.with_is_favorite(PhotoQueries.shuffled(seed), self.request.user)


@extend_schema(
    summary='Фото галереи',
    description='Сначала новые. 404 проверяется раньше параметров пагинации.',
    responses={200: PhotoSerializer(many=True), 400: BAD_PARAMS, 404: NOT_FOUND},
)
class GalleryPhotoListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real request
            return Photo.objects.none()
        photos = get_object_or_404(Gallery, pk=self.kwargs['pk']).photos.all()
        return PhotoQueries.with_is_favorite(photos, self.request.user)


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
        return PhotoQueries.with_is_favorite(PhotoQueries.favorites_of(self.request.user), self.request.user)


class FavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Добавить фото в избранное', request=None,
        responses={204: OpenApiResponse(description='Добавлено (или уже было)'), 401: UNAUTHORIZED,
                   404: OpenApiResponse(description='Фото с таким id нет')},
    )
    def put(self, request, photo_id):
        try:
            FavoriteService.add(request.user, photo_id)
        except Photo.DoesNotExist:
            raise NotFound('Фото не найдено.')
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Убрать фото из избранного',
        responses={204: OpenApiResponse(description='Убрано (или его и не было)'), 401: UNAUTHORIZED},
    )
    def delete(self, request, photo_id):
        FavoriteService.remove(request.user, photo_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
