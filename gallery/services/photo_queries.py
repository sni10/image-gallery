from django.conf import settings
from django.db.models import (
    BooleanField, Case, CharField, Count, Exists, IntegerField, OuterRef, Q, QuerySet, Subquery, Value, When,
)
from django.db.models.expressions import RawSQL
from django.db.models.functions import MD5, Cast, Concat

from ..models import Favorite, Photo


class PhotoQueries:
    """Read-side queries for photos across all galleries."""

    @staticmethod
    def shuffled(seed: str) -> QuerySet[Photo]:
        """Pseudo-random order that is stable for a given seed, so pages of one seed never repeat or skip photos."""
        # ponytail: md5 of every row + sort per page; fine for ~100k photos, precompute a random column if it gets slow
        shuffle_key = MD5(Concat(Cast('pk', CharField()), Value(seed)))
        return Photo.objects.annotate(shuffle_key=shuffle_key).order_by('shuffle_key', 'pk')

    @staticmethod
    def favorites_of(user) -> QuerySet[Photo]:
        """The user's favorite photos, most recently added first."""
        added_at = Favorite.objects.filter(user=user, photo=OuterRef('pk')).values('created_at')[:1]
        return (
            Photo.objects.annotate(favorited_at=Subquery(added_at))
            .filter(favorited_at__isnull=False)
            .order_by('-favorited_at', '-pk')
        )

    @staticmethod
    def neighbors(photo: Photo) -> tuple[str | None, str | None]:
        """Public ids of the photos before and after `photo` in its gallery, in the gallery list order (-id).
        Two indexed single-row queries, never the whole gallery."""
        ids = Photo.objects.filter(gallery_id=photo.gallery_id).values_list('public_id', flat=True)
        return ids.filter(pk__gt=photo.pk).order_by('pk').first(), ids.filter(pk__lt=photo.pk).order_by('-pk').first()

    @staticmethod
    def with_locked(photos: QuerySet[Photo], user) -> QuerySet[Photo]:
        """Annotate `locked`: a guest gets the original only for the GUEST_FREE_PHOTOS newest photos of each gallery
        (gallery list order, -id). Signed-in users: never locked.
        Not a window function: GET /photos/{id} selects one row, where a row number would always be 1."""
        if user.is_authenticated:
            return photos.annotate(locked=Value(False, output_field=BooleanField()))
        return photos.annotate(locked=_beyond_guest_free())

    @staticmethod
    def for_user(photos: QuerySet[Photo], user) -> QuerySet[Photo]:
        """Both annotations PhotoSerializer reads: `is_favorite` and `locked`."""
        return PhotoQueries.with_locked(PhotoQueries.with_is_favorite(photos, user), user)

    @staticmethod
    def newest() -> QuerySet[Photo]:
        return Photo.objects.order_by('-created_at', '-pk')

    @staticmethod
    def popular() -> QuerySet[Photo]:
        """Most favorited first. The count orders only, it is never exposed.
        ponytail: Count over all favorites per request; denormalize Photo.favorites_count if it gets slow."""
        return Photo.objects.annotate(favorites_n=Count('favorited_by')).order_by('-favorites_n', '-pk')

    @staticmethod
    def search(photos: QuerySet[Photo], q: str) -> QuerySet[Photo]:
        """Case-insensitive substring in a tag, the description, the title, the gallery or category title.
        Photo columns have trigram indexes; gallery and category tables are small.
        ponytail: plain "contains"; TrigramWordSimilarity with a threshold and ranking if that proves too little."""
        return photos.filter(Q(tags_text__icontains=q) | Q(description__icontains=q) | Q(title__icontains=q)
                             | Q(gallery__title__icontains=q) | Q(gallery__category__title__icontains=q))

    @staticmethod
    def guest_feed(feed: QuerySet[Photo]) -> QuerySet[Photo]:
        """The home feed for a guest: photos open in their galleries first (still in the feed's order), then the
        rest. Annotates `guest_free`; the view opens only the first GUEST_FREE_PHOTOS positions, so any seed or sort
        shows originals a guest can see in the galleries anyway: trying them never reveals new ones."""
        return feed.annotate(guest_free=~_beyond_guest_free()).order_by('-guest_free', *feed.query.order_by)

    @staticmethod
    def similar(photo: Photo) -> QuerySet[Photo]:
        """Photos sharing the most tags with `photo`, other galleries first among equals (its own gallery is a
        click away). Then the rest: same category first, then any, newest first (fills up a short list).
        ponytail: tag intersection over every row, no index; a GIN index on tags when the catalog gets large."""
        shared = RawSQL(f'cardinality(ARRAY(SELECT unnest({Photo._meta.db_table}.tags) '
                        'INTERSECT SELECT unnest(%s::varchar[])))', (photo.tags,), output_field=IntegerField())
        other_gallery = Case(When(gallery_id=photo.gallery_id, then=0), default=1)
        filler_same_category = Case(When(shared=0, gallery__category_id=photo.gallery.category_id, then=1), default=0)
        return (Photo.objects.exclude(pk=photo.pk)
                .annotate(shared=shared, other_gallery=other_gallery, filler_same_category=filler_same_category)
                .order_by('-shared', '-filler_same_category', '-other_gallery', '-pk'))

    @staticmethod
    def with_is_favorite(photos: QuerySet[Photo], user) -> QuerySet[Photo]:
        """Annotate `is_favorite` for `user` with one EXISTS subquery (no N+1); always False for anonymous."""
        if not user.is_authenticated:
            return photos.annotate(is_favorite=Value(False, output_field=BooleanField()))
        return photos.annotate(is_favorite=Exists(Favorite.objects.filter(user=user, photo=OuterRef('pk'))))


def _beyond_guest_free():
    """True when the gallery has at least GUEST_FREE_PHOTOS newer photos than this one."""
    n = settings.GUEST_FREE_PHOTOS
    newer = Photo.objects.filter(gallery=OuterRef('gallery'), pk__gt=OuterRef('pk')).order_by()
    return Exists(newer[n - 1:n])
