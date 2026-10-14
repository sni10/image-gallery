from io import StringIO

import yaml
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

PATHS = {
    '/photos', '/photos/{photo_id}', '/categories', '/galleries', '/galleries/{id}', '/galleries/{id}/photos',
    '/auth/register', '/auth/confirm-email', '/auth/resend-confirmation', '/auth/password-reset', '/auth/password-reset/confirm',
    '/auth/login', '/auth/refresh',
    '/auth/logout', '/auth/confirm-email-change', '/me', '/me/email', '/me/password',
    '/me/favorites', '/me/favorites/{photo_id}', '/ingest/photos', '/complaints', '/photos/{photo_id}/similar',
    '/me/collections', '/me/collections/{id}', '/me/collections/{id}/photos', '/me/collections/{id}/photos/{photo_id}',
    '/tags',
}


class OpenApiSchemaTest(SimpleTestCase):
    def setUp(self):
        out = StringIO()
        call_command('spectacular', '--validate', '--fail-on-warn', stdout=out)  # raises on warnings
        self.schema = yaml.safe_load(out.getvalue())

    def responses(self, path, method):
        return set(self.schema['paths'][path][method]['responses'])

    def test_gallery_contract(self):
        schema = self.schema
        self.assertEqual(set(schema['paths']), PATHS)
        self.assertEqual(self.responses('/galleries/{id}/photos', 'get'), {'200', '400', '404'})
        page = schema['components']['schemas']['PaginatedGalleryList']
        self.assertEqual(page['required'], ['items', 'total'])
        photo = schema['components']['schemas']['Photo']['properties']
        self.assertEqual(photo['url']['format'], 'uri')
        self.assertEqual(photo['isFavorite']['type'], 'boolean')
        self.assertTrue(schema['components']['schemas']['Gallery']['properties']['cover']['nullable'])
        for path, method in (('/galleries/{id}', 'get'), ('/galleries/{id}/photos', 'get'),
                             ('/me/favorites/{photo_id}', 'put'), ('/me/favorites/{photo_id}', 'delete')):
            param = next(p for p in schema['paths'][path][method]['parameters'] if p['in'] == 'path')
            self.assertEqual(param['schema']['type'], 'string')
            self.assertIn('Публичный id', param['description'])
        for name in ('Gallery', 'Photo', 'Category'):
            self.assertIn('Публичный id', schema['components']['schemas'][name]['properties']['id']['description'])
        self.assertIn('category', schema['components']['schemas']['Gallery']['required'])
        catalog_params = {p['name'] for p in schema['paths']['/galleries']['get']['parameters']}
        self.assertEqual(catalog_params, {'page', 'limit', 'category', 'q'})
        categories = schema['paths']['/categories']['get']['responses']['200']['content']['application/json']['schema']
        self.assertEqual(categories['type'], 'array')  # not paginated
        self.assertEqual(set(schema['components']['schemas']['CategoryWithCount']['required']),
                         {'id', 'slug', 'title', 'galleriesCount'})

    def test_auth_contract(self):
        self.assertEqual(self.schema['components']['securitySchemes']['bearerAuth'],
                         {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'})
        self.assertEqual(self.responses('/auth/login', 'post'), {'200', '401', '403', '429'})
        self.assertEqual(self.responses('/me/password', 'post'), {'200', '400', '401', '429'})
        self.assertEqual(self.responses('/me', 'delete'), {'204', '400', '401', '403', '429'})
        self.assertEqual(self.responses('/me/favorites/{photo_id}', 'put'), {'204', '401', '404'})
        login_body = self.schema['paths']['/auth/login']['post']['requestBody']['content']['application/json']
        self.assertEqual(login_body['schema']['$ref'], '#/components/schemas/Login')
        self.assertEqual(set(self.schema['components']['schemas']['TokenPair']['required']), {'access', 'refresh'})

    def test_register_contract(self):
        register = self.schema['components']['schemas']['Register']
        self.assertEqual(set(register['required']), {'email', 'password', 'termsAccepted', 'termsVersion'})
        self.assertEqual(register['properties']['termsAccepted']['type'], 'boolean')

    @override_settings(COMPLAINTS_EMAIL='secret-admin@example.com')
    def test_complaints_contract(self):
        self.assertEqual(self.responses('/complaints', 'post'), {'204', '400', '429'})
        self.assertEqual(set(self.schema['components']['schemas']['Complaint']['required']), {'email', 'message'})
        out = StringIO()
        call_command('spectacular', stdout=out)
        self.assertNotIn('secret-admin', out.getvalue())

    def test_feed_similar_collections_contract(self):
        sort = next(p for p in self.schema['paths']['/photos']['get']['parameters'] if p['name'] == 'sort')
        self.assertEqual(set(sort['schema']['enum']), {'random', 'new', 'popular'})
        self.assertEqual(self.responses('/photos/{photo_id}/similar', 'get'), {'200', '400', '404'})
        self.assertEqual(self.responses('/me/collections/{id}/photos/{photo_id}', 'put'), {'204', '400', '401', '404'})
        collection = self.schema['components']['schemas']['CollectionWithCover']
        self.assertEqual(set(collection['required']), {'id', 'title', 'photosCount', 'cover'})  # hasPhoto optional
        self.assertIn('hasPhoto', collection['properties'])

    def test_ingest_contract(self):
        ingest = self.schema['paths']['/ingest/photos']['post']
        self.assertEqual(set(ingest['responses']), {'200', '201', '400', '403', '404'})
        self.assertEqual(list(ingest['requestBody']['content']), ['multipart/form-data'])
        self.assertNotIn({'bearerAuth': []}, ingest.get('security', []))  # X-Api-Key, not the JWT
        self.assertLessEqual({'description', 'tags'}, set(self.schema['components']['schemas']['Photo']['properties']))


class OpenApiPagesTest(TestCase):
    def test_docs_pages(self):
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
        self.assertContains(self.client.get('/api/docs/'), 'swagger-ui')
        self.assertContains(self.client.get('/api/redoc/'), 'redoc')


