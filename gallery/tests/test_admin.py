import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from ..models import Gallery, Photo
from ..services import PhotoService
from .utils import gallery, image, jpeg


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GalleryAdminTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', password='x'))
        self.gallery = gallery('Main')
        self.other = gallery('Other')
        service = PhotoService()
        self.a, self.b, self.c = (service.create(jpeg(800, 600, f'{n}.jpg'), self.gallery) for n in 'abc')
        self.url = f'/admin/gallery/gallery/{self.gallery.pk}/change/'

    def post(self, **data):
        return self.client.post(self.url, {'title': 'Main', **data})

    def test_photo_section_removed(self):
        self.assertEqual(self.client.get('/admin/gallery/photo/').status_code, 404)

    def test_list_shows_cover_and_count(self):
        r = self.client.get('/admin/gallery/gallery/')
        self.assertContains(r, '/media/thumb/')
        self.assertContains(r, 'случайная')

    def test_change_page_has_photo_grid(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'enctype="multipart/form-data"')
        for photo in (self.a, self.b, self.c):
            self.assertContains(r, photo.thumb.url)
            self.assertContains(r, f'name="selected" value="{photo.pk}"')
        self.assertContains(r, 'name="cover" value="" checked')

    def test_create_gallery_with_upload(self):
        files = [jpeg(4000, 3000, 'x.jpg'), jpeg(600, 800, 'y.jpg')]
        r = self.client.post('/admin/gallery/gallery/add/', {'title': 'New', 'new_images': files})
        self.assertEqual(r.status_code, 302)
        new = Gallery.objects.get(title='New')
        self.assertEqual(sorted(new.photos.values_list('title', flat=True)), ['x', 'y'])
        x = new.photos.get(title='x')
        self.assertEqual((x.width, x.height), (4000, 3000))
        self.assertEqual(Image.open(x.image).size, (4000, 3000))  # original, not resized
        thumb = Image.open(x.thumb)
        self.assertEqual((thumb.format, thumb.size), ('WEBP', (400, 300)))

    def test_upload_into_existing_gallery(self):
        self.assertEqual(self.post(new_images=[jpeg(100, 100, 'd.jpg')]).status_code, 302)
        self.assertEqual(self.gallery.photos.count(), 4)

    def test_upload_rejects_non_image(self):
        r = self.post(new_images=[SimpleUploadedFile('bad.jpg', b'nope')])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.gallery.photos.count(), 3)

    def test_upload_rejects_format_browsers_cant_show(self):
        r = self.post(new_images=[image(10, 10, 'scan.tif', 'TIFF')])
        self.assertContains(r, 'формат TIFF не поддерживается')
        self.assertEqual(self.gallery.photos.count(), 3)

    def test_choose_and_reset_cover(self):
        self.post(cover=self.b.pk)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover, self.b)
        self.assertContains(self.client.get(self.url), f'name="cover" value="{self.b.pk}" checked')

        self.post(cover='')
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover)

    def test_cover_from_other_gallery_rejected(self):
        foreign = PhotoService().create(jpeg(10, 10), self.other)
        self.assertEqual(self.post(cover=foreign.pk).status_code, 200)
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover)

    def test_move_selected(self):
        self.post(cover=self.a.pk)
        self.post(cover=self.a.pk, selected=[self.a.pk, self.b.pk], move_to=self.other.pk)
        self.assertEqual(list(self.gallery.photos.all()), [self.c])
        self.assertEqual(self.other.photos.count(), 2)
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover)  # the cover left the gallery -> back to random

    def test_delete_selected(self):
        self.post(cover=self.c.pk, selected=[self.c.pk], delete_selected='on')
        self.assertEqual(set(self.gallery.photos.all()), {self.a, self.b})
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover)

    def test_selection_action_validation(self):
        self.assertEqual(self.post(move_to=self.other.pk).status_code, 200)  # nothing selected
        both = self.post(selected=[self.a.pk], move_to=self.other.pk, delete_selected='on')
        self.assertEqual(both.status_code, 200)
        self.assertEqual(Photo.objects.filter(gallery=self.gallery).count(), 3)
