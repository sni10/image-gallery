from io import StringIO

import yaml
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase


class OpenApiSchemaTest(SimpleTestCase):
    def test_schema_is_valid_and_matches_contract(self):
        out = StringIO()
        call_command('spectacular', '--validate', '--fail-on-warn', stdout=out)  # raises on warnings
        schema = yaml.safe_load(out.getvalue())

        self.assertLessEqual({'/photos', '/galleries', '/galleries/{id}', '/galleries/{id}/photos'}, set(schema['paths']))
        self.assertEqual(set(schema['paths']['/galleries/{id}/photos']['get']['responses']), {'200', '400', '404'})
        page = schema['components']['schemas']['PaginatedGalleryList']
        self.assertEqual(page['required'], ['items', 'total'])
        photo = schema['components']['schemas']['Photo']['properties']
        self.assertEqual(photo['url']['format'], 'uri')
        self.assertTrue(schema['components']['schemas']['Gallery']['properties']['cover']['nullable'])
        self.assertEqual(schema['components']['securitySchemes']['bearerAuth'], {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'})


class OpenApiPagesTest(TestCase):
    def test_docs_pages(self):
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
        self.assertContains(self.client.get('/api/docs/'), 'swagger-ui')
        self.assertContains(self.client.get('/api/redoc/'), 'redoc')
