import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .utils import bearer, gallery, photo


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class GalleryCoverTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('a@example.com', 'a@example.com', 'x', is_staff=True)
        cls.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        cls.g = gallery('Own')
        cls.p1, cls.p2 = photo(cls.g), photo(cls.g)
        cls.foreign = photo(gallery('Other'))

    def patch(self, cover, user=None):
        auth = bearer(user) if user else {}
        return self.client.patch(f'/galleries/{self.g.public_id}', {'cover': cover, 'title': 'ignored'},
                                 content_type='application/json', **auth)

    def get(self):
        return self.client.get(f'/galleries/{self.g.public_id}').json()

    def test_set_and_clear(self):
        r = self.patch(self.p2.public_id, self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['coverId'], r.json()['cover']['id'], r.json()['title']), (self.p2.public_id,) * 2 + ('Own',))
        self.assertEqual(self.get()['coverId'], self.p2.public_id)
        r = self.patch(None, self.admin)
        self.assertEqual((r.status_code, r.json()['coverId']), (200, None))
        self.assertIn(r.json()['cover']['id'], {self.p1.public_id, self.p2.public_id})  # random again

    def test_rejects_foreign_or_unknown_photo(self):
        self.patch(self.p1.public_id, self.admin)
        for cover in (self.foreign.public_id, 'nope'):
            with self.subTest(cover=cover):
                r = self.patch(cover, self.admin)
                self.assertEqual((r.status_code, set(r.json())), (400, {'cover'}))
        self.assertEqual(self.get()['coverId'], self.p1.public_id)

    def test_access(self):
        self.assertEqual(self.patch(self.p1.public_id).status_code, 401)
        self.assertEqual(self.patch(self.p1.public_id, self.user).status_code, 403)
        r = self.client.patch('/galleries/nope', {'cover': None}, content_type='application/json', **bearer(self.admin))
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(self.get()['coverId'])

    def test_deleted_cover(self):
        self.patch(self.p1.public_id, self.admin)
        self.p1.delete()
        self.assertIsNone(self.get()['coverId'])

    def test_list_has_cover_id(self):
        self.patch(self.p1.public_id, self.admin)
        items = {g['id']: g for g in self.client.get('/galleries').json()['items']}
        self.assertEqual(items[self.g.public_id]['coverId'], self.p1.public_id)
        self.assertIsNone(items[self.foreign.gallery.public_id]['coverId'])
