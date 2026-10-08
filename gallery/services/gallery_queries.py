from django.db.models import Count, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce

from ..models import Gallery, Photo
from .photo_queries import PhotoQueries


class GalleryQueries:
    """Read-side queries for galleries: photo counts and the cover to display."""

    @staticmethod
    def with_stats() -> QuerySet[Gallery]:
        """Annotates `photos_count` and `display_cover_id`: the chosen cover if it still belongs
        to the gallery, otherwise a random photo of the gallery (new on every query)."""
        chosen_cover = Photo.objects.filter(pk=OuterRef('cover_id'), gallery=OuterRef('pk')).values('pk')[:1]
        # ponytail: ORDER BY random() per gallery scans its photos; fine for thousands per gallery,
        # switch to a random offset over an indexed column if galleries get much bigger
        random_photo = Photo.objects.filter(gallery=OuterRef('pk')).order_by('?').values('pk')[:1]
        # Count via subquery, not Count('photos'): a GROUP BY would also group by the random cover and duplicate rows
        photos_count = (
            Photo.objects.filter(gallery=OuterRef('pk')).order_by().values('gallery').annotate(n=Count('pk')).values('n')
        )
        return Gallery.objects.annotate(
            photos_count=Coalesce(Subquery(photos_count), 0),
            display_cover_id=Coalesce(Subquery(chosen_cover), Subquery(random_photo)),
        )

    @staticmethod
    def attach_covers(galleries: list[Gallery], user) -> list[Gallery]:
        """Set `gallery.display_cover` (Photo or None, with `is_favorite` for `user`) for galleries
        from with_stats(), in one query."""
        photos = PhotoQueries.with_is_favorite(Photo.objects.all(), user)
        covers = photos.in_bulk([g.display_cover_id for g in galleries if g.display_cover_id])
        for gallery in galleries:
            gallery.display_cover = covers.get(gallery.display_cover_id)
        return galleries
