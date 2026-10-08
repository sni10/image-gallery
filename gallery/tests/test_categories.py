import tempfile

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from ..models import Category, Gallery
from .utils import gallery, make_category


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CategoryModelTest(TestCase):
    def test_gallery_requires_category(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Gallery.objects.create(title='No category')
        with self.assertRaises(ValidationError) as ctx:
            Gallery(title='No category').full_clean()
        self.assertIn('category', ctx.exception.message_dict)

    def test_non_empty_category_cannot_be_deleted(self):
        ai = make_category('ai')
        gallery('G', ai)
        with self.assertRaises(ProtectedError):
            ai.delete()
        make_category('empty').delete()  # an empty one can

    def test_slug_rules(self):
        make_category('comics')
        for slug in ('Комиксы!', 'with space', 'comics', 'COMICS'):
            with self.subTest(slug=slug):
                with self.assertRaises(ValidationError) as ctx:
                    Category(title='X', slug=slug).full_clean()
                self.assertIn('slug', ctx.exception.message_dict)
        category = Category(title='AI', slug='AI-Art')
        category.full_clean()
        self.assertEqual(category.slug, 'ai-art')

    def test_order(self):
        make_category('b', 'B', position=1)
        make_category('a', 'A', position=1)
        make_category('z', 'Z', position=0)
        self.assertEqual(list(Category.objects.values_list('slug', flat=True)), ['z', 'a', 'b'])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CategoryApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ai = make_category('ai', 'AI', position=2)
        cls.comics = make_category('comics', 'Комиксы', position=1)
        cls.empty = make_category('photo', 'Фото', position=0)
        cls.ai_galleries = [gallery(f'AI {i}', cls.ai) for i in range(3)]
        cls.comic = gallery('Comic', cls.comics)

    def ids(self, response):
        return [g['id'] for g in response.json()['items']]

    # 2.1
    def test_categories_list(self):
        r = self.client.get('/categories')  # no auth needed
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [
            {'id': str(self.comics.pk), 'slug': 'comics', 'title': 'Комиксы', 'galleriesCount': 1},
            {'id': str(self.ai.pk), 'slug': 'ai', 'title': 'AI', 'galleriesCount': 3},
        ])  # empty "Фото" hidden, ordered by position

    # 2.2
    def test_category_in_gallery(self):
        expected = {'id': str(self.comics.pk), 'slug': 'comics', 'title': 'Комиксы'}
        self.assertEqual(self.client.get(f'/galleries/{self.comic.pk}').json()['category'], expected)
        items = self.client.get('/galleries').json()['items']
        self.assertTrue(all(set(g['category']) == {'id', 'slug', 'title'} for g in items))

    def test_catalog_queries_do_not_grow_with_galleries(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get('/galleries')
            return len(ctx.captured_queries)

        before = count()
        for i in range(5):
            gallery(f'More {i}', make_category(f'c{i}'))
        self.assertEqual(count(), before)

    # 2.3
    def test_filter_by_category(self):
        r = self.client.get('/galleries?category=ai')
        self.assertEqual((sorted(self.ids(r)), r.json()['total']), (sorted(str(g.pk) for g in self.ai_galleries), 3))
        self.assertEqual(self.client.get('/galleries').json()['total'], 4)
        self.assertEqual(self.client.get('/galleries?category=nope').json(), {'items': [], 'total': 0})
        self.assertEqual(self.client.get('/galleries?category=photo').json(), {'items': [], 'total': 0})
        page = self.client.get('/galleries?category=ai&page=2&limit=2').json()
        self.assertEqual((len(page['items']), page['total']), (1, 3))
