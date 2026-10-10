import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.services.access_tokens import AccessTokenService

from ..models import Category, Gallery, Photo
from ..services import FavoriteService, PhotoService
from .utils import gallery, jpeg


def split(dt):
    """Admin SplitDateTime widget values (seconds precision, current time zone)."""
    local = timezone.localtime(dt)
    return {'link_date_0': local.strftime('%Y-%m-%d'), 'link_date_1': local.strftime('%H:%M:%S')}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp())
class ReissueLinksAdminTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='x')
        self.client.force_login(self.admin)
        self.gallery = gallery('G')
        service = PhotoService()
        self.a, self.b = (service.create(jpeg(100 + i, 100), self.gallery) for i in range(2))

    def change_url(self, g):
        return f'/admin/gallery/gallery/{g.pk}/change/'

    def post_gallery(self, **data):
        g = Gallery.objects.get(pk=self.gallery.pk)
        payload = {'title': g.title, 'category': g.category_id, **split(g.link_date), **data}
        return self.client.post(self.change_url(g), payload)

    # 4.1
    def test_untouched_form_keeps_public_id(self):
        old = self.gallery.public_id
        self.assertEqual(self.post_gallery(title='Renamed').status_code, 302)
        self.assertEqual(Gallery.objects.get(pk=self.gallery.pk).public_id, old)

    def test_editing_link_date_reissues_id(self):
        old = self.gallery.public_id
        self.post_gallery(**split(self.gallery.link_date + timedelta(days=1)))
        new = Gallery.objects.get(pk=self.gallery.pk).public_id
        self.assertNotEqual(new, old)
        self.assertEqual(self.client.get(f'/galleries/{old}').status_code, 404)
        self.assertEqual(self.client.get(f'/galleries/{new}').status_code, 200)

    def test_gallery_reissue_action(self):
        old, created = self.gallery.public_id, self.gallery.created_at
        r = self.client.post('/admin/gallery/gallery/', {'action': 'reissue_links', '_selected_action': [self.gallery.pk]})
        self.assertEqual(r.status_code, 302)
        g = Gallery.objects.get(pk=self.gallery.pk)
        self.assertNotEqual(g.public_id, old)
        self.assertEqual(g.created_at, created)
        self.assertEqual(self.client.get(f'/galleries/{old}').status_code, 404)
        self.assertEqual(self.client.get(f'/galleries/{g.public_id}').status_code, 200)

    def test_category_reissue_action(self):
        category = self.gallery.category
        old = category.public_id
        self.client.post('/admin/gallery/category/', {'action': 'reissue_links', '_selected_action': [category.pk]})
        new = Category.objects.get(pk=category.pk).public_id
        self.assertNotEqual(new, old)
        self.assertEqual([c['id'] for c in self.client.get('/categories').json()], [new])
        self.assertContains(self.client.get(f'/admin/gallery/category/{category.pk}/change/'), new)

    # 4.2
    def test_user_reissue_action(self):
        user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        old = user.profile.public_id
        self.assertContains(self.client.get(f'/admin/auth/user/{user.pk}/change/'), old)
        self.client.post('/admin/auth/user/', {'action': 'reissue_links', '_selected_action': [user.pk]})
        user = User.objects.get(pk=user.pk)
        self.assertNotEqual(user.profile.public_id, old)
        me = self.client.get('/me', HTTP_AUTHORIZATION=f'Bearer {AccessTokenService().issue(user)}').json()
        self.assertEqual(me['id'], user.profile.public_id)

    def test_add_user_page_still_works(self):
        r = self.client.post('/admin/auth/user/add/', {
            'username': 'new@example.com', 'password1': 'correct-horse-battery', 'password2': 'correct-horse-battery',
            'usable_password': 'true',
        })
        self.assertEqual(r.status_code, 302)
        self.assertRegex(User.objects.get(username='new@example.com').profile.public_id, r'^[a-z2-7]{26}$')

    # 4.3
    def test_reissue_selected_photos(self):
        FavoriteService.add(self.admin, self.a.public_id)
        old_a, old_b = self.a.public_id, self.b.public_id
        self.assertEqual(self.post_gallery(selected=[self.a.pk], reissue_selected='on').status_code, 302)
        new_a = Photo.objects.get(pk=self.a.pk).public_id
        self.assertNotEqual(new_a, old_a)
        self.assertEqual(Photo.objects.get(pk=self.b.pk).public_id, old_b)
        self.assertTrue(self.admin.favorites.filter(photo=self.a).exists())  # favorites point to the pk
        self.assertEqual(self.client.put(f'/me/favorites/{old_a}').status_code, 401)  # session admin is not API auth

    def test_one_grid_action_at_a_time(self):
        r = self.post_gallery(selected=[self.a.pk], reissue_selected='on', delete_selected='on')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Photo.objects.get(pk=self.a.pk).public_id, self.a.public_id)
