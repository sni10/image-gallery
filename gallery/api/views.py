from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView

from ..models import Gallery, Photo
from ..services import GalleryQueries
from .pagination import PageLimitPagination
from .serializers import GallerySerializer, PhotoSerializer

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
        return GalleryQueries.attach_covers(super().paginate_queryset(queryset))


@extend_schema(summary='Галерея', responses={200: GallerySerializer, 404: NOT_FOUND})
class GalleryDetailView(RetrieveAPIView):
    serializer_class = GallerySerializer

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def get_object(self):
        return GalleryQueries.attach_covers([super().get_object()])[0]


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
        return get_object_or_404(Gallery, pk=self.kwargs['pk']).photos.all()
