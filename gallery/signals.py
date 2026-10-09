from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Photo


@receiver(post_delete, sender=Photo)
def delete_unused_files(sender, instance, **kwargs):
    """Remove the photo's files once nothing points to them. Files are content-addressed (see store_once),
    so another photo may share them. Runs after commit: a rolled back delete keeps its files.
    Fires for every path: PhotoService.delete, admin, gallery cascade."""
    def cleanup():
        for field_file in (instance.image, instance.thumb):
            name = field_file.name
            if name and not Photo.objects.filter(Q(image=name) | Q(thumb=name)).exists():
                field_file.storage.delete(name)

    transaction.on_commit(cleanup)
