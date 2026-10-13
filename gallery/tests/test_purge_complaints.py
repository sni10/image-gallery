from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from ..models import Complaint


@override_settings(COMPLAINTS_RETENTION_DAYS=1095)
class PurgeOldComplaintsTest(TestCase):
    def test_deletes_only_older_than_retention(self):
        now = timezone.now()
        for days in (1096, 1094, 0):
            c = Complaint.objects.create(email='a@example.com', message='x' * 10)
            Complaint.objects.filter(pk=c.pk).update(created_at=now - timedelta(days=days))  # auto_now_add
        out = StringIO()
        call_command('purge_old_complaints', stdout=out)
        self.assertIn('Deleted complaints: 1', out.getvalue())
        self.assertEqual(Complaint.objects.count(), 2)
        self.assertFalse(Complaint.objects.filter(created_at__lt=now - timedelta(days=1095)).exists())
