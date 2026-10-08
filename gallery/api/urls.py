from django.urls import path

from .views import GalleryDetailView, GalleryListView, GalleryPhotoListView

urlpatterns = [
    path('galleries', GalleryListView.as_view(), name='gallery-list'),
    path('galleries/<int:pk>', GalleryDetailView.as_view(), name='gallery-detail'),
    path('galleries/<int:pk>/photos', GalleryPhotoListView.as_view(), name='gallery-photos'),
]
