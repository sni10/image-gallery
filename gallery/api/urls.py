from django.urls import path

from .views import (
    CategoryListView, FavoriteListView, FavoriteView, GalleryDetailView, GalleryListView, GalleryPhotoListView,
    RandomPhotoListView,
)

urlpatterns = [
    path('photos', RandomPhotoListView.as_view(), name='photo-list'),
    path('categories', CategoryListView.as_view(), name='category-list'),
    path('galleries', GalleryListView.as_view(), name='gallery-list'),
    path('galleries/<str:id>', GalleryDetailView.as_view(), name='gallery-detail'),
    path('galleries/<str:id>/photos', GalleryPhotoListView.as_view(), name='gallery-photos'),
    path('me/favorites', FavoriteListView.as_view(), name='favorite-list'),
    path('me/favorites/<str:photo_id>', FavoriteView.as_view(), name='favorite'),
]
