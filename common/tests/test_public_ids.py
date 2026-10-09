from datetime import UTC, datetime, timedelta, timezone

from django.test import SimpleTestCase, override_settings

from ..public_ids import make_public_id

WHEN = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)


class MakePublicIdTest(SimpleTestCase):
    def test_format(self):
        self.assertRegex(make_public_id('gallery.gallery', 8, WHEN), r'^[a-z2-7]{26}$')

    def test_deterministic_and_timezone_independent(self):
        moscow = WHEN.astimezone(timezone(timedelta(hours=3)))
        self.assertEqual(make_public_id('gallery.gallery', 8, WHEN), make_public_id('gallery.gallery', 8, moscow))

    def test_any_input_changes_the_id(self):
        base = make_public_id('gallery.gallery', 8, WHEN)
        others = {
            make_public_id('gallery.photo', 8, WHEN),
            make_public_id('gallery.gallery', 9, WHEN),
            make_public_id('gallery.gallery', 8, WHEN + timedelta(microseconds=1)),
        }
        self.assertNotIn(base, others)
        self.assertEqual(len(others), 3)

    def test_depends_on_secret(self):
        with override_settings(SECRET_KEY='another-secret-key-' + 'x' * 40):
            other = make_public_id('gallery.gallery', 8, WHEN)
        self.assertNotEqual(make_public_id('gallery.gallery', 8, WHEN), other)
