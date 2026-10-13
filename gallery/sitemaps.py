from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.db.models import Max

from .models import Category, Gallery, Photo


class FrontendSitemap(Sitemap):
    """Pages of the SPA (FRONTEND_URL), not of the API host that renders the sitemap."""

    def get_domain(self, site=None):
        return urlsplit(settings.FRONTEND_URL).netloc

    def get_protocol(self, protocol=None):
        return urlsplit(settings.FRONTEND_URL).scheme


class PageSitemap(FrontendSitemap):
    def items(self):
        return ['/', '/galleries', '/terms']

    def location(self, item):
        return item


class CategorySitemap(FrontendSitemap):
    def items(self):  # only categories with photos, like the catalog
        return (Category.objects.annotate(updated=Max('galleries__photos__created_at'))
                .filter(updated__isnull=False).order_by('position', 'title'))

    def location(self, item):
        return f'/categories/{item.slug}'

    def lastmod(self, item):
        return item.updated


class GallerySitemap(FrontendSitemap):
    def items(self):
        return (Gallery.objects.annotate(updated=Max('photos__created_at'))
                .filter(updated__isnull=False, public_id__isnull=False).order_by('pk'))

    def location(self, item):
        return f'/galleries/{item.public_id}'

    def lastmod(self, item):
        return item.updated


class PhotoSitemap(FrontendSitemap):
    # ponytail: one file, Django caps each section at 50 000 urls; switch to sitemaps.views.index near that
    def items(self):
        return Photo.objects.filter(public_id__isnull=False).only('public_id', 'created_at').order_by('pk')

    def location(self, item):
        return f'/photos/{item.public_id}'

    def lastmod(self, item):
        return item.created_at


SITEMAPS = {'pages': PageSitemap, 'categories': CategorySitemap, 'galleries': GallerySitemap, 'photos': PhotoSitemap}
