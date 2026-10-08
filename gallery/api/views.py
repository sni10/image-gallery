from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView

from ..models import Gallery
from ..services import GalleryQueries
from .pagination import PageLimitPagination
from .serializers import GallerySerializer, PhotoSerializer


class GalleryListView(ListAPIView):
    serializer_class = GallerySerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def paginate_queryset(self, queryset):
        return GalleryQueries.attach_covers(super().paginate_queryset(queryset))


class GalleryDetailView(RetrieveAPIView):
    serializer_class = GallerySerializer

    def get_queryset(self):
        return GalleryQueries.with_stats()

    def get_object(self):
        return GalleryQueries.attach_covers([super().get_object()])[0]


class GalleryPhotoListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination

    def get_queryset(self):
        return get_object_or_404(Gallery, pk=self.kwargs['pk']).photos.all()
