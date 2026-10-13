from django.urls import path

from .complaints import ComplaintView

from .views import (
    CategoryListView, FavoriteListView, FavoriteView, GalleryDetailView, GalleryListView, GalleryPhotoListView,
    PhotoDetailView, PhotoIngestView, RandomPhotoListView, SimilarPhotoListView,
)

urlpatterns = [
    path('photos', RandomPhotoListView.as_view(), name='photo-list'),
    path('photos/<str:photo_id>', PhotoDetailView.as_view(), name='photo-detail'),
    path('photos/<str:photo_id>/similar', SimilarPhotoListView.as_view(), name='photo-similar'),
    path('categories', CategoryListView.as_view(), name='category-list'),
    path('galleries', GalleryListView.as_view(), name='gallery-list'),
    path('galleries/<str:id>', GalleryDetailView.as_view(), name='gallery-detail'),
    path('galleries/<str:id>/photos', GalleryPhotoListView.as_view(), name='gallery-photos'),
    path('me/favorites', FavoriteListView.as_view(), name='favorite-list'),
    path('me/favorites/<str:photo_id>', FavoriteView.as_view(), name='favorite'),
    path('ingest/photos', PhotoIngestView.as_view(), name='photo-ingest'),
    path('complaints', ComplaintView.as_view(), name='complaints'),
]
