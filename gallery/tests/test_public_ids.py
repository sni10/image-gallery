import importlib
import tempfile
from datetime import timedelta

from django.test import TestCase, override_settings

from common.public_ids import make_public_id

from ..models import Category, Gallery
from ..services import PhotoService
from .utils import gallery, jpeg, make_category

migration = importlib.import_module('gallery.migrations.0009_public_ids')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp())
class PublicIdModelTest(TestCase):
    def test_new_record_gets_link_date_and_id(self):
        category = make_category('ai')
        self.assertEqual(category.link_date, category.created_at)
        self.assertRegex(category.public_id, r'^[a-z2-7]{26}$')
        self.assertEqual(category.public_id, make_public_id('gallery.category', category.pk, category.created_at))
        reloaded = Category.objects.get(pk=category.pk)
        self.assertEqual((reloaded.link_date, reloaded.public_id), (category.link_date, category.public_id))

    def test_all_models_get_ids(self):
        g = gallery('G')
        photo = PhotoService().create(jpeg(10, 10), g)
        for obj in (g, g.category, photo):
            self.assertRegex(obj.public_id, r'^[a-z2-7]{26}$')
        self.assertEqual(len({g.public_id, g.category.public_id, photo.public_id}), 3)

    def test_id_stable_unless_link_date_changes(self):
        g = gallery('G')
        original = g.public_id
        g.title = 'Renamed'
        g.category = make_category('other')
        g.save()
        g = Gallery.objects.get(pk=g.pk)
        g.save()
        self.assertEqual(g.public_id, original)
        with override_settings(SECRET_KEY='rotated-secret-key-' + 'x' * 40):
            g.title = 'After key rotation'
            g.save()
        self.assertEqual(Gallery.objects.get(pk=g.pk).public_id, original)  # published links survive rotation

    def test_changing_link_date_changes_id(self):
        g = Gallery.objects.get(pk=gallery('G').pk)
        original, created = g.public_id, g.created_at
        g.link_date = g.link_date + timedelta(days=1)
        g.save()
        self.assertNotEqual(g.public_id, original)
        self.assertEqual(Gallery.objects.get(pk=g.pk).public_id, g.public_id)

        previous = g.public_id
        g.reissue_link()
        g.refresh_from_db()
        self.assertNotIn(g.public_id, (original, previous))
        self.assertEqual(g.created_at, created)

    def test_migration_copy_matches_code(self):
        when = make_category('ai').created_at
        self.assertEqual(migration.public_id('gallery.gallery', 42, when), make_public_id('gallery.gallery', 42, when))
