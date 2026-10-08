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
    def with_is_favorite(photos: QuerySet[Photo], user) -> QuerySet[Photo]:
        """Annotate `is_favorite` for `user` with one EXISTS subquery (no N+1); always False for anonymous."""
        if not user.is_authenticated:
            return photos.annotate(is_favorite=Value(False, output_field=BooleanField()))
        return photos.annotate(is_favorite=Exists(Favorite.objects.filter(user=user, photo=OuterRef('pk'))))
