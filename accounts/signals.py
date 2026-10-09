from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, raw=False, **kwargs):
    """Every user gets a profile (and so a public id) as soon as it is created."""
    if created and not raw:
        Profile.objects.create(user=instance)
