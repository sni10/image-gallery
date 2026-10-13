from django.db import transaction
from django.db.models import Count, Exists, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Collection, CollectionPhoto, Photo
from .photo_queries import PhotoQueries


class LimitReached(Exception):
    pass


class CollectionService:
    """A user's own collections. Callers look a collection up by user first: another user's one is a 404.
    ponytail: the count limits are checked before insert, two parallel requests can go one over. Harmless."""

    @staticmethod
    def create(user, title: str) -> Collection:
        if user.collections.count() >= Collection.MAX_PER_USER:
            raise LimitReached(f'At most {Collection.MAX_PER_USER} collections.')
        return Collection.objects.create(user=user, title=title)

    @staticmethod
    def rename(collection: Collection, title: str) -> Collection:
        collection.title = title
        collection.save(update_fields=['title', 'updated_at'])
        return collection

    @staticmethod
    @transaction.atomic
    def add_photo(collection: Collection, photo_public_id: str) -> None:
        """Idempotent. Raises Photo.DoesNotExist or LimitReached."""
        photo = Photo.objects.get(public_id=photo_public_id)
        if collection.links.filter(photo=photo).exists():
            return
        if collection.links.count() >= Collection.MAX_PHOTOS:
            raise LimitReached(f'At most {Collection.MAX_PHOTOS} photos in a collection.')
        _, created = CollectionPhoto.objects.get_or_create(collection=collection, photo=photo)
        if created:
            _touch(collection)

    @staticmethod
    def remove_photo(collection: Collection, photo_public_id: str) -> None:
        if collection.links.filter(photo__public_id=photo_public_id).delete()[0]:
            _touch(collection)


class CollectionQueries:
    @staticmethod
    def of_user(user, photo_public_id: str | None = None) -> QuerySet[Collection]:
        """Recently changed first. Annotates `photos_count`, `cover_id` (last added photo) and, for a photo id,
        `has_photo`."""
        links = CollectionPhoto.objects.filter(collection=OuterRef('pk'))
        collections = user.collections.annotate(
            photos_count=Coalesce(Subquery(
                links.order_by().values('collection').annotate(n=Count('pk')).values('n')), 0),
            cover_id=Subquery(links.order_by('-added_at', '-pk').values('photo_id')[:1]),
        ).order_by('-updated_at', '-pk')
        if photo_public_id is not None:
            collections = collections.annotate(has_photo=Exists(links.filter(photo__public_id=photo_public_id)))
        return collections

    @staticmethod
    def attach_covers(collections, user) -> list[Collection]:
        """Set `collection.cover` (Photo with `is_favorite`/`locked` for `user`, or None) in one query."""
        collections = list(collections)
        photos = PhotoQueries.for_user(Photo.objects.all(), user)
        covers = photos.in_bulk([c.cover_id for c in collections if c.cover_id])
        for collection in collections:
            collection.cover = covers.get(collection.cover_id)
        return collections

    @staticmethod
    def photos(collection: Collection) -> QuerySet[Photo]:
        """Recently added first."""
        return (Photo.objects.filter(collection_links__collection=collection)
                .order_by('-collection_links__added_at', '-pk'))


def _touch(collection: Collection) -> None:
    Collection.objects.filter(pk=collection.pk).update(updated_at=timezone.now())
