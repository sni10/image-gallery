import tempfile

from django.test import TestCase, override_settings

from ..models import Gallery
from ..services import PhotoService
from .utils import gallery, jpeg, make_category

PHOTO_KEYS = {'id', 'title', 'description', 'tags', 'url', 'thumbUrl', 'width', 'height', 'isFavorite', 'locked',
              'gallery'}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')  # URLs must not depend on local .env
class GalleryApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empty = gallery('Empty')
        cls.full = gallery('Full')
        service = PhotoService()
        cls.photo_ids = {service.create(jpeg(1600, 1067), cls.full, f'Photo #{i}').public_id for i in range(3)}
        cls.other = gallery('Other')
        service.create(jpeg(800, 600), cls.other)

    def test_list(self):
        data = self.client.get('/galleries?page=1&limit=2').json()
        self.assertEqual(data['total'], 3)
        newest, full = data['items']  # newest first
        self.assertEqual(newest['title'], 'Other')
        self.assertEqual(full, {**full, 'id': self.full.public_id, 'title': 'Full', 'photosCount': 3})
        self.assertEqual(set(full['cover']), PHOTO_KEYS)
        self.assertIn(full['cover']['id'], self.photo_ids)  # cover is a photo of this very gallery

    def test_empty_gallery_has_null_cover(self):
        data = self.client.get('/galleries?page=2&limit=2').json()
        self.assertEqual(data['items'], [{'id': self.empty.public_id, 'title': 'Empty', 'description': '', 'photosCount': 0, 'cover': None, 'coverId': None,
                           'category': {'id': self.empty.category.public_id, 'slug': 'test', 'title': 'Test'}}])

    def test_page_past_end_is_empty(self):
        self.assertEqual(self.client.get('/galleries?page=99').json(), {'items': [], 'total': 3})

    def test_search_by_title(self):
        nature = make_category('nature')
        mountains, _ = gallery('Горы Алтая', nature), gallery('Горы Кавказа')  # second one in category "test"
        titles = lambda query: [g['title'] for g in self.client.get(f'/galleries{query}').json()['items']]
        self.assertEqual(titles('?q=горы'), ['Горы Кавказа', 'Горы Алтая'])  # case-insensitive Cyrillic
        self.assertEqual(titles('?q=ULL'), ['Full'])  # part of the title
        self.assertEqual(titles('?q=горы&category=nature'), [mountains.title])
        self.assertEqual(titles('?q=%20%20'), titles(''))  # blank q = no filter (covers are random, compare titles)
        self.assertEqual(titles('?q='), titles(''))
        self.assertEqual(self.client.get('/galleries?q=nothing').json(), {'items': [], 'total': 0})
        self.assertEqual(self.client.get(f'/galleries?q={"x" * 100}').status_code, 200)
        r = self.client.get(f'/galleries?q={"x" * 101}')
        self.assertEqual((r.status_code, list(r.json())), (400, ['q']))

    def test_invalid_params(self):
        self.assertEqual(self.client.get('/galleries?page=0').status_code, 400)
        self.assertEqual(self.client.get(f'/galleries/{self.full.public_id}/photos?limit=x').status_code, 400)

    def test_detail(self):
        data = self.client.get(f'/galleries/{self.full.public_id}').json()
        self.assertEqual((data['title'], data['photosCount']), ('Full', 3))
        self.assertIn(data['cover']['id'], self.photo_ids)
        self.assertEqual(self.client.get('/galleries/999999').status_code, 404)

    def test_chosen_cover_is_stable(self):
        chosen = self.full.photos.last()
        Gallery.objects.filter(pk=self.full.pk).update(cover=chosen)
        covers = {self.client.get(f'/galleries/{self.full.public_id}').json()['cover']['id'] for _ in range(5)}
        self.assertEqual(covers, {chosen.public_id})

    def test_stale_cover_from_other_gallery_ignored(self):
        foreign = self.other.photos.get()
        Gallery.objects.filter(pk=self.full.pk).update(cover=foreign)
        self.assertIn(self.client.get(f'/galleries/{self.full.public_id}').json()['cover']['id'], self.photo_ids)

    def test_gallery_photos(self):
        data = self.client.get(f'/galleries/{self.full.public_id}/photos?page=1&limit=2').json()
        self.assertEqual(data['total'], 3)
        self.assertEqual(len(data['items']), 2)
        item = data['items'][0]
        self.assertEqual(set(item), PHOTO_KEYS)
        self.assertEqual((item['width'], item['height']), (1600, 1067))  # original size
        self.assertRegex(item['url'], r'^http://testserver/media/original/\w\w/\w\w/\w{64}\.jpg\?exp=\d+&sig=\w{64}$')  # signed, expiring
        self.assertRegex(item['thumbUrl'], r'^http://testserver/media/thumb/\w\w/\w\w/\w{64}\.webp$')
        self.assertLessEqual({p['id'] for p in data['items']}, self.photo_ids)
        self.assertEqual(self.client.get(f'/galleries/{self.empty.public_id}/photos').json(), {'items': [], 'total': 0})
        self.assertEqual(self.client.get('/galleries/999999/photos').status_code, 404)
