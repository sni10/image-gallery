from django.db.models import CharField, QuerySet, Value
from django.db.models.functions import MD5, Cast, Concat

from ..models import Photo


class PhotoQueries:
    """Read-side queries for photos across all galleries."""

    @staticmethod
    def shuffled(seed: str) -> QuerySet[Photo]:
        """Pseudo-random order that is stable for a given seed, so pages of one seed never repeat or skip photos."""
        # ponytail: md5 of every row + sort per page; fine for ~100k photos, precompute a random column if it gets slow
        shuffle_key = MD5(Concat(Cast('pk', CharField()), Value(seed)))
        return Photo.objects.annotate(shuffle_key=shuffle_key).order_by('shuffle_key', 'pk')
