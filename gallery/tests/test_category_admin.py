import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from ..models import Category, Gallery
from .utils import gallery, make_category


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CategoryAdminTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', password='x'))
        self.ai = make_category('ai', 'AI')
        self.comics = make_category('comics', 'Комиксы')
        self.g = gallery('G', self.ai)

    # 3.1
    def test_list_and_create(self):
        r = self.client.get('/admin/gallery/category/')
        self.assertContains(r, 'Комиксы')
        self.assertContains(r, 'name="form-0-position"')  # position editable in the list
        self.assertContains(self.client.get('/admin/gallery/category/add/'), 'prepopulated')

        r = self.client.post('/admin/gallery/category/add/', {'title': 'Фото', 'slug': 'photo', 'position': 3})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Category.objects.get(slug='photo').title, 'Фото')

    def test_invalid_slug_rejected(self):
        r = self.client.post('/admin/gallery/category/add/', {'title': 'X', 'slug': 'Комиксы!', 'position': 0})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Category.objects.filter(title='X').exists())

    def test_non_empty_category_not_deleted(self):
        r = self.client.post(f'/admin/gallery/category/{self.ai.pk}/delete/', {'post': 'yes'})
        self.assertEqual(r.status_code, 200)  # "cannot delete ... protected objects" page
        self.assertContains(r, 'G')
        self.assertTrue(Category.objects.filter(pk=self.ai.pk).exists())

    # 3.2
    def test_gallery_without_category_rejected(self):
        r = self.client.post('/admin/gallery/gallery/add/', {'title': 'No category'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('category', r.context['adminform'].form.errors)
        self.assertFalse(Gallery.objects.filter(title='No category').exists())

    def test_change_category_moves_gallery(self):
        r = self.client.post(f'/admin/gallery/gallery/{self.g.pk}/change/', {'title': 'G', 'category': self.comics.pk})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get('/galleries?category=comics').json()['total'], 1)
        self.assertEqual(self.client.get('/galleries?category=ai').json()['total'], 0)

    def test_gallery_list_column_and_filter(self):
        gallery('Comic gallery', self.comics)
        r = self.client.get('/admin/gallery/gallery/')
        self.assertContains(r, 'Комиксы')
        filtered = self.client.get(f'/admin/gallery/gallery/?category__id__exact={self.comics.pk}')
        self.assertEqual([g.title for g in filtered.context['cl'].result_list], ['Comic gallery'])
