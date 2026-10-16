"""Visual recommendations on PhotoEmbedding vectors (pgvector, cosine): "similar photos" and "my wave".
ponytail: full scan of all vectors, no HNSW index; fine up to ~30k photos, add the index when a query passes 50 ms."""
import random
from collections import Counter

from django.db.models import Q
from pgvector.django import CosineDistance

from ..models import Favorite, Photo, PhotoEmbedding
from .photo_queries import PhotoQueries

CANDIDATES = 200  # nearest vectors re-scored for "similar"
VECTOR_WEIGHT, TAG_WEIGHT = 0.75, 0.25
NEAR_DUPLICATE = 0.97  # cosine similarity above this = the same picture (crop, re-save, small variation)
PER_GALLERY = 3  # a gallery is a photo set: at most this many of one set in a list
ANCHORS = 6
WAVE_MIN_ANCHORS = 3  # fewer favorites with a vector: cold start
DISCOVERY_EVERY = 8  # every 8th place of the wave is a random photo


def similar_ids(photo: Photo, limit: int) -> list[int]:
    """Photo pks for the "similar" block: nearest by vector re-scored with shared tags, no near-duplicates, at most
    PER_GALLERY per gallery; filled up by tags. No vector: by tags only, exactly as before vectors."""
    by_tags = PhotoQueries.similar(photo)
    if not (embedding := PhotoEmbedding.objects.filter(photo=photo).first()):
        return list(by_tags.values_list('pk', flat=True)[:limit])
    rows = _nearest(embedding, CANDIDATES, Q(photo=photo))
    tags = set(photo.tags)
    scored = sorted(((VECTOR_WEIGHT * cos + TAG_WEIGHT * _jaccard(tags, set(row_tags)), pk, gallery)
                     for pk, gallery, row_tags, cos in rows if cos <= NEAR_DUPLICATE), reverse=True)
    picker = _Picker(limit, banned={pk for pk, _, _, cos in rows if cos > NEAR_DUPLICATE})
    picker.fill(iter((pk, gallery) for _, pk, gallery in scored))
    # ponytail: the filler walks at most 4*limit tag matches, so the gallery cap can leave the list a bit short
    picker.fill(iter(by_tags.exclude(pk__in=picker.banned).values_list('pk', 'gallery_id')[:limit * 4]))
    return picker.ids


def wave_ids(user, exclude: list[str], limit: int) -> list[int]:
    """Photo pks for the next page of the user's wave. `exclude`: public ids already shown; the user's favorites
    are never shown. Round-robin over the neighbors of a few favorites, every DISCOVERY_EVERY-th place random.
    Cold start (too few favorites with a vector): popular photos mixed with random ones."""
    excluded = {*Photo.objects.filter(public_id__in=exclude).values_list('pk', flat=True),
                *Favorite.objects.filter(user=user).values_list('photo_id', flat=True)}
    anchors = _anchors(user)
    if len(anchors) < WAVE_MIN_ANCHORS:
        picker = _Picker(limit, excluded)
        popular = PhotoQueries.popular().exclude(pk__in=excluded).values_list('pk', 'gallery_id')[:limit]
        anything = Photo.objects.exclude(pk__in=excluded).order_by('?').values_list('pk', 'gallery_id')[:limit]
        _round_robin(picker, [iter(popular), iter(anything)])
        return picker.ids
    neighbors = [_nearest(anchor, limit * 2, Q(photo_id__in=excluded)) for anchor in anchors]
    # ponytail: near-duplicates of the anchors only, not of every favorite; compare with all if dupes slip through
    duplicates = {pk for rows in neighbors for pk, _, _, cos in rows if cos > NEAR_DUPLICATE}
    picker = _Picker(limit, excluded | duplicates)
    discovery = iter(PhotoEmbedding.objects.exclude(photo_id__in=excluded).order_by('?')
                     .values_list('photo_id', 'photo__gallery_id')[:limit * 2])
    _round_robin(picker, [iter((pk, gallery) for pk, gallery, _, _ in rows) for rows in neighbors], discovery)
    picker.fill(discovery)  # the anchors ran dry: the rest is random
    return picker.ids


def photos_in_order(ids: list[int], user) -> list[Photo]:
    """The photos of `ids` in that order, annotated for PhotoSerializer."""
    by_pk = PhotoQueries.for_user(Photo.objects.filter(pk__in=ids), user).in_bulk()
    return [by_pk[pk] for pk in ids if pk in by_pk]


def _nearest(embedding: PhotoEmbedding, n: int, exclude: Q) -> list[tuple[int, int, list[str], float]]:
    """(photo pk, gallery id, tags, cosine similarity) of the n nearest vectors of the same model."""
    rows = (PhotoEmbedding.objects.filter(model=embedding.model).exclude(exclude)
            .annotate(distance=CosineDistance('vector', embedding.vector)).order_by('distance')
            .values_list('photo_id', 'photo__gallery_id', 'photo__tags', 'distance')[:n])
    return [(pk, gallery, tags, 1 - distance) for pk, gallery, tags, distance in rows]


def _anchors(user) -> list[PhotoEmbedding]:
    """Up to ANCHORS random favorites with a vector, recent ones more likely. Not one averaged vector: with mixed
    tastes the average lands in a "middle" nobody likes.
    ponytail: random anchors instead of k-means; k-means when random anchors make the wave one-sided."""
    favorites = (Favorite.objects.filter(user=user, photo__embedding__isnull=False)
                 .order_by('-created_at').values_list('photo_id', flat=True))
    # weighted sample without replacement (Efraimidis-Spirakis), weight 1/(rank+1): key = random() ** (rank+1)
    chosen = sorted(enumerate(favorites), key=lambda r: random.random() ** (r[0] + 1), reverse=True)[:ANCHORS]
    return list(PhotoEmbedding.objects.filter(photo_id__in=[pk for _, pk in chosen]))


def _round_robin(picker, streams, discovery=None):
    """One photo from each stream in turn until the picker is full or the streams run dry; with `discovery`,
    every DISCOVERY_EVERY-th place comes from it."""
    while streams and not picker.full:
        for stream in list(streams):
            if not picker.full and discovery and len(picker.ids) % DISCOVERY_EVERY == DISCOVERY_EVERY - 1:
                picker.take(discovery)
            if picker.full:
                return
            if not picker.take(stream):
                streams.remove(stream)


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


class _Picker:
    """Collects photo pks in order: no repeats, nothing banned, at most PER_GALLERY per gallery."""

    def __init__(self, limit, banned=()):
        self.ids, self.limit, self.banned, self.per_gallery = [], limit, set(banned), Counter()

    @property
    def full(self):
        return len(self.ids) >= self.limit

    def take(self, rows) -> bool:
        """Add the first acceptable (pk, gallery id) of the iterator; False when it ran dry."""
        for pk, gallery in rows:
            if pk not in self.banned and self.per_gallery[gallery] < PER_GALLERY:
                self.banned.add(pk)
                self.ids.append(pk)
                self.per_gallery[gallery] += 1
                return True
        return False

    def fill(self, rows):
        while not self.full and self.take(rows):
            pass
