import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from ..models import Favorite
from .utils import bearer, gallery, photo


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/', GUEST_FREE_PHOTOS=10)
class FeedSortTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        cls.big = [photo(gallery('Big')) for _ in range(12)]  # oldest first; the 2 oldest are locked for guests
        cls.small = [photo(gallery('Small')) for _ in range(3)]
        cls.all = cls.big + cls.small
        cls.guest_free = {p.public_id for p in cls.big[2:] + cls.small}
        fans = [User.objects.create_user(f'f{i}@example.com', f'f{i}@example.com', 'x') for i in range(3)]
        cls.top, cls.second = cls.big[0], cls.small[0]  # top is guest-locked in its gallery
        for fan in fans:
            Favorite.objects.create(user=fan, photo=cls.top)
        Favorite.objects.create(user=fans[0], photo=cls.second)

    def ids(self, query, user=None, limit=50):
        r = self.client.get(f'/photos?{query}&limit={limit}', **(bearer(user) if user else {}))
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()['items']

    def test_new(self):
        expected = [p.public_id for p in reversed(self.all)]
        self.assertEqual([p['id'] for p in self.ids('sort=new', self.user)], expected)

    def test_popular(self):
        rest = [p.public_id for p in reversed(self.all) if p not in (self.top, self.second)]
        items = self.ids('sort=popular', self.user)
        self.assertEqual([p['id'] for p in items], [self.top.public_id, self.second.public_id, *rest])
        self.assertNotIn('favoritesCount', items[0])

    def test_guest_gets_only_ten_open_from_guest_free_photos(self):
        for sort in ('new', 'popular', 'random&seed=abc'):
            with self.subTest(sort=sort):
                pages = [self.ids(f'sort={sort}&page={page}', limit=4) for page in (1, 2, 3, 4)]
                items = [p for page in pages for p in page]
                self.assertEqual(len(items), 15)
                self.assertEqual([p['locked'] for p in items], [False] * 10 + [True] * 5)
                self.assertLessEqual({p['id'] for p in items[:10]}, self.guest_free)
                self.assertTrue(all(p['url'] is None for p in items[10:]))

    def test_guest_popular_keeps_order_inside_open_photos(self):
        items = self.ids('sort=popular')
        self.assertEqual(items[0]['id'], self.second.public_id)  # top is locked in its gallery: goes after the open
        self.assertEqual(items[13]['id'], self.top.public_id)  # after all 13 guest-free photos

    def test_errors(self):
        self.assertEqual(self.client.get('/photos?sort=best').status_code, 400)
        self.assertIn('sort', self.client.get('/photos?sort=best').json())
        self.assertIn('seed', self.client.get('/photos').json())  # random is the default and needs a seed
        self.assertEqual(self.client.get('/photos?sort=new').status_code, 200)
