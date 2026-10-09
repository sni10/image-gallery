import hashlib
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import QuerySet

from ..models import Gallery, Photo
from .image_processor import ImageProcessor


class PhotoService:
    """Single entry point for writing photos: create, replace the image, rebuild thumb, move, delete."""

    def __init__(self, processor: ImageProcessor | None = None):
        self._processor = processor or ImageProcessor()

    def create(self, file, gallery: Gallery, title: str = '') -> Photo:
        photo = Photo(gallery=gallery, title=title)
        self.apply_image(photo, file)
        photo.save()
        return photo

    def apply_image(self, photo: Photo, file) -> None:
        """Store `file` untouched as the original (named by its SHA-256) plus a WebP thumb. Does not save the photo."""
        processed = self._processor.process(file)
        path = sharded_path(file_sha256(file))
        photo.title = photo.title or Path(file.name).stem
        photo.width, photo.height = processed.width, processed.height
        store_once(photo.image, f'{path}.{processed.extension}', file)
        store_once(photo.thumb, f'{path}.webp', ContentFile(processed.thumb))

    def rebuild_thumb(self, photo: Photo) -> None:
        """Regenerate the thumb (and size) from the stored original, e.g. after changing thumb settings."""
        with photo.image.open('rb') as original:
            processed = self._processor.process(original)
            path = sharded_path(file_sha256(original))
        name = f'{path}.webp'
        photo.thumb.storage.delete(photo.thumb.field.generate_filename(photo, name))  # overwrite, not suffix
        photo.width, photo.height = processed.width, processed.height
        photo.thumb.save(name, ContentFile(processed.thumb), save=False)
        photo.save(update_fields=['thumb', 'width', 'height'])

    @staticmethod
    @transaction.atomic
    def move(photos: QuerySet[Photo], gallery: Gallery) -> int:
        """Move photos to `gallery`; galleries that used one of them as cover fall back to random."""
        ids = list(photos.values_list('pk', flat=True))
        Gallery.objects.filter(cover__in=ids).exclude(pk=gallery.pk).update(cover=None)
        return Photo.objects.filter(pk__in=ids).update(gallery=gallery)

    @staticmethod
    def reissue_links(photos: QuerySet[Photo]) -> int:
        """New public ids for these photos; old ids return 404. Favorites and covers point to the pk, so they stay."""
        photos = list(photos)
        for photo in photos:
            photo.reissue_link()
        return len(photos)

    @staticmethod
    def delete(photos: QuerySet[Photo]) -> int:
        """Delete photos; a gallery whose cover is deleted falls back to random (FK is SET_NULL).
        Unused files are removed by the post_delete signal (gallery/signals.py)."""
        deleted, _ = photos.delete()
        return deleted


def store_once(field_file, name: str, content) -> None:
    """Content-addressed save: `name` is derived from the content hash, so an existing file with that name
    already holds identical bytes - point to it instead of writing a suffixed duplicate.
    Several photos may then share one file: never delete files of a single photo without checking others."""
    full_name = field_file.field.generate_filename(field_file.instance, name)
    if field_file.storage.exists(full_name):
        field_file.name = full_name
    else:
        field_file.save(name, content, save=False)


def file_sha256(file) -> str:
    digest = hashlib.sha256()
    for chunk in file.chunks():  # chunks() rewinds to the start
        digest.update(chunk)
    return digest.hexdigest()


def sharded_path(digest: str) -> str:
    """'ab/cd/abcd…' (64 hex): unique per content, two-level sharding keeps directories small."""
    return f'{digest[:2]}/{digest[2:4]}/{digest}'
