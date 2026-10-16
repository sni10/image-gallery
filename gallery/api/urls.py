from django.urls import path

from .collections import CollectionDetailView, CollectionListView, CollectionPhotoListView, CollectionPhotoView
from .complaints import ComplaintView
from .embeddings import EmbeddingView
from .views import (
    CategoryListView, FavoriteListView, FavoriteView, GalleryDetailView, GalleryListView, GalleryPhotoListView,
    PhotoDetailView, PhotoIngestView, RandomPhotoListView, SimilarPhotoListView, TagListView,
)

urlpatterns = [
    path('photos', RandomPhotoListView.as_view(), name='photo-list'),
    path('photos/<str:photo_id>', PhotoDetailView.as_view(), name='photo-detail'),
    path('photos/<str:photo_id>/similar', SimilarPhotoListView.as_view(), name='photo-similar'),
    path('tags', TagListView.as_view(), name='tag-list'),
    path('categories', CategoryListView.as_view(), name='category-list'),
    path('galleries', GalleryListView.as_view(), name='gallery-list'),
    path('galleries/<str:id>', GalleryDetailView.as_view(), name='gallery-detail'),
    path('galleries/<str:id>/photos', GalleryPhotoListView.as_view(), name='gallery-photos'),
    path('me/favorites', FavoriteListView.as_view(), name='favorite-list'),
    path('me/favorites/<str:photo_id>', FavoriteView.as_view(), name='favorite'),
    path('me/collections', CollectionListView.as_view(), name='collection-list'),
    path('me/collections/<str:id>', CollectionDetailView.as_view(), name='collection-detail'),
    path('me/collections/<str:id>/photos', CollectionPhotoListView.as_view(), name='collection-photos'),
    path('me/collections/<str:id>/photos/<str:photo_id>', CollectionPhotoView.as_view(), name='collection-photo'),
    path('ingest/photos', PhotoIngestView.as_view(), name='photo-ingest'),
    path('ingest/embeddings', EmbeddingView.as_view(), name='embeddings'),
    path('complaints', ComplaintView.as_view(), name='complaints'),
]
