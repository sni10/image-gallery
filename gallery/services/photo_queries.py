from django.conf import settings
from django.db.models import BooleanField, CharField, Exists, OuterRef, QuerySet, Subquery, Value
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
    def with_locked(photos: QuerySet[Photo], user, all_locked: bool = False) -> QuerySet[Photo]:
        """Annotate `locked`: a guest gets the original only for the GUEST_FREE_PHOTOS newest photos of each gallery
        (gallery list order, -id), nothing at all with `all_locked` (the home feed). Signed-in users: never locked.
        Not a window function: GET /photos/{id} selects one row, where a row number would always be 1."""
        if user.is_authenticated:
            return photos.annotate(locked=Value(False, output_field=BooleanField()))
        if all_locked:
            return photos.annotate(locked=Value(True, output_field=BooleanField()))
        n = settings.GUEST_FREE_PHOTOS
        newer = Photo.objects.filter(gallery=OuterRef('gallery'), pk__gt=OuterRef('pk')).order_by()
        return photos.annotate(locked=Exists(newer[n - 1:n]))  # at least n newer photos in the gallery

    @staticmethod
    def for_user(photos: QuerySet[Photo], user, all_locked: bool = False) -> QuerySet[Photo]:
        """Both annotations PhotoSerializer reads: `is_favorite` and `locked`."""
        return PhotoQueries.with_locked(PhotoQueries.with_is_favorite(photos, user), user, all_locked)

    @staticmethod
    def with_is_favorite(photos: QuerySet[Photo], user) -> QuerySet[Photo]:
        """Annotate `is_favorite` for `user` with one EXISTS subquery (no N+1); always False for anonymous."""
        if not user.is_authenticated:
            return photos.annotate(is_favorite=Value(False, output_field=BooleanField()))
        return photos.annotate(is_favorite=Exists(Favorite.objects.filter(user=user, photo=OuterRef('pk'))))
