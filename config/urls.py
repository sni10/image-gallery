from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from gallery.sitemaps import SITEMAPS

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='sitemap'),  # served at artai.win/sitemap.xml (Caddy)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('', include('accounts.api.urls')),
    path('', include('gallery.api.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # only works with DEBUG=True
