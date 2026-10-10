import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from gallery.services import PhotoService
from gallery.tests.utils import gallery, jpeg


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), ORIGINALS_ROOT=tempfile.mkdtemp(), MEDIA_URL='/media/')  # relative, as in production
class HttpsBehindProxyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gallery = gallery('G')
        PhotoService().create(jpeg(10, 10), cls.gallery)

    def photo_urls(self, **headers):
        items = self.client.get(f'/galleries/{self.gallery.public_id}/photos', **headers).json()['items']
        return items[0]['url'], items[0]['thumbUrl']

    @override_settings(ALLOWED_HOSTS=['api.example.test'])
    def test_image_urls_follow_forwarded_proto(self):
        host = {'HTTP_HOST': 'api.example.test'}  # a real proxy always passes Host
        for url in self.photo_urls(HTTP_X_FORWARDED_PROTO='https', **host):
            self.assertTrue(url.startswith('https://api.example.test/media/'), url)
        for url in self.photo_urls(**host):
            self.assertTrue(url.startswith('http://api.example.test/media/'), url)

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_admin_login_over_https_with_secure_cookies(self):
        User.objects.create_superuser('admin', password='correct-horse-battery')
        client = self.client_class(enforce_csrf_checks=True)
        https = {'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_HOST': 'secure.example.test'}
        with override_settings(ALLOWED_HOSTS=['secure.example.test']):
            page = client.get('/admin/login/', secure=False, **https)
            self.assertTrue(page.cookies['csrftoken']['secure'])
            r = client.post('/admin/login/?next=/admin/', {
                'username': 'admin', 'password': 'correct-horse-battery',
                'csrfmiddlewaretoken': page.cookies['csrftoken'].value,
            }, HTTP_ORIGIN='https://secure.example.test', HTTP_REFERER='https://secure.example.test/admin/login/', **https)
        self.assertEqual(r.status_code, 302)  # CSRF passed, logged in
        self.assertTrue(r.cookies['sessionid']['secure'])
