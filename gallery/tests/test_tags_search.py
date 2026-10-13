import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from ..models import Favorite
from .utils import bearer, gallery, make_category, photo


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/', GUEST_FREE_PHOTOS=10, FRONTEND_URL='https://artai.win')
class TagFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        g = gallery('Mixed')
        cls.cats = [photo(g, ['cat', 'neon']) for _ in range(3)]
        cls.dog = photo(g, ['dog', 'neon'])
        cls.catalog = photo(g, ['catalog'])  # contains "cat" as a substring, not the tag
        Favorite.objects.create(user=cls.user, photo=cls.cats[0])

    def get(self, query, user=None):
        return self.client.get(f'/photos?{query}', **(bearer(user) if user else {}))

    def ids(self, query, user=None):
        r = self.get(query, user)
        self.assertEqual(r.status_code, 200, r.content)
        return [p['id'] for p in r.json()['items']]

    def test_exact_tag_normalized(self):
        expected = [p.public_id for p in reversed(self.cats)]
        for tag in ('cat', 'Cat', '%23cat', '%20cat%20', '%23CAT'):
            with self.subTest(tag=tag):
                self.assertEqual(self.ids(f'tag={tag}&sort=new', self.user), expected)

    def test_with_popular_and_empty_result(self):
        ids = self.ids('tag=cat&sort=popular', self.user)
        self.assertEqual(ids[0], self.cats[0].public_id)
        self.assertEqual(set(ids), {p.public_id for p in self.cats})
        r = self.get('tag=nothing&sort=new')
        self.assertEqual((r.status_code, r.json()), (200, {'items': [], 'total': 0}))

    def test_bad_tag(self):
        for tag in ('', '%20', '%23', 'x' * 51):
            with self.subTest(tag=tag):
                r = self.get(f'tag={tag}&sort=new')
                self.assertEqual(r.status_code, 400)
                self.assertIn('tag', r.json())

    def test_guest_locks_by_position_in_tag_results(self):
        g = gallery('Twelve')
        twelve = [photo(g, ['z']) for _ in range(12)]  # the 2 oldest are locked in their gallery
        items = self.get('tag=z&sort=new&limit=20').json()['items']
        self.assertEqual([p['locked'] for p in items], [False] * 10 + [True] * 2)
        self.assertEqual({p['id'] for p in items[10:]}, {twelve[0].public_id, twelve[1].public_id})

    def test_sitemap_lists_tags_with_three_photos(self):
        photo(gallery('Spaces'), ['big cat']), photo(gallery('Spaces2'), ['big cat'])
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('<loc>https://artai.win/tags/cat</loc>', body)
        self.assertIn('<loc>https://artai.win/tags/neon</loc>', body)  # 4 photos
        for absent in ('dog', 'catalog', 'big%20cat'):
            self.assertNotIn(f'/tags/{absent}<', body)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')
class SearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('u@example.com', 'u@example.com', 'x')
        art, comics = make_category('art', 'Digital Art'), make_category('comics', 'Комиксы')
        city, heroes = gallery('Night City', art), gallery('Heroes', comics)
        cls.neon = photo(city, ['neon', 'cat'])
        cls.described = photo(city)
        cls.described.description = 'A glowing NEON sign'
        cls.described.save()
        cls.hero = photo(heroes, ['hero'])
        cls.plain = photo(heroes, ['dog'])

    def ids(self, query):
        r = self.client.get(f'/photos?{query}&sort=new', **bearer(self.user))
        self.assertEqual(r.status_code, 200, r.content)
        return {p['id'] for p in r.json()['items']}

    def test_finds_by_tag_part_description_gallery_and_category(self):
        cases = {
            'eo': {self.neon, self.described},  # part of a tag and of the description
            'NeOn': {self.neon, self.described},
            'night%20ci': {self.neon, self.described},  # gallery title
            'комикс': {self.hero, self.plain},  # category title, case-insensitive Cyrillic
            'digital': {self.neon, self.described},
            'zzz': set(),
        }
        for q, expected in cases.items():
            with self.subTest(q=q):
                self.assertEqual(self.ids(f'q={q}'), {p.public_id for p in expected})

    def test_q_and_tag_intersect(self):
        self.assertEqual(self.ids('q=neon&tag=cat'), {self.neon.public_id})

    def test_bad_q(self):
        for q in ('a', '%20a%20', 'x' * 101):
            with self.subTest(q=q):
                r = self.client.get(f'/photos?q={q}&sort=new')
                self.assertEqual(r.status_code, 400)
                self.assertIn('q', r.json())
        self.assertEqual(self.client.get('/photos?q=a').json()['q'], ['Ensure this field has at least 2 characters.'])

    def test_tag_text_follows_tags(self):
        self.plain.tags = ['wolf']
        self.plain.save(update_fields=['tags'])
        self.assertEqual(self.ids('q=wolf'), {self.plain.public_id})
