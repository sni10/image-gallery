from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Complaint


class Command(BaseCommand):
    help = 'Delete complaints older than COMPLAINTS_RETENTION_DAYS (privacy policy). Run daily (cron, DEPLOY.md).'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.COMPLAINTS_RETENTION_DAYS)
        deleted, _ = Complaint.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f'Deleted complaints: {deleted}')
