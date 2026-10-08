from django.core.management.base import BaseCommand

from ...models import Photo
from ...services import PhotoService


class Command(BaseCommand):
    help = 'Regenerate WebP thumbnails (and stored sizes) from the original files.'

    def handle(self, *args, **options):
        service = PhotoService()
        count = 0
        for photo in Photo.objects.iterator():
            service.rebuild_thumb(photo)
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Rebuilt thumbnails: {count}'))
