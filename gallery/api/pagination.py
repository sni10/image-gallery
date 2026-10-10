from rest_framework.exceptions import ValidationError
from rest_framework.pagination import BasePagination
from rest_framework.response import Response


class PageLimitPagination(BasePagination):
    """?page=1&limit=20 -> {"items": [...], "total": N}. A page past the end returns empty items, not 404."""

    default_limit = 20
    max_limit = 100

    def paginate_queryset(self, queryset, request, view=None):
        page = self._positive_int(request, 'page', 1)
        limit = min(self._positive_int(request, 'limit', self.default_limit), self.max_limit)
        self.total = queryset.count()
        self.offset = offset = (page - 1) * limit  # position of the first item in the whole list
        return list(queryset[offset:offset + limit])

    def get_paginated_response(self, data):
        return Response({'items': data, 'total': self.total})

    # OpenAPI (drf-spectacular): query params and the {items, total} envelope
    def get_schema_operation_parameters(self, view):
        return [
            {
                'name': 'page', 'in': 'query', 'required': False,
                'description': 'Номер страницы, с 1. Страница за пределами total вернёт пустой items.',
                'schema': {'type': 'integer', 'minimum': 1, 'default': 1},
            },
            {
                'name': 'limit', 'in': 'query', 'required': False,
                'description': f'Размер страницы. Больше {self.max_limit} обрезается до {self.max_limit}.',
                'schema': {'type': 'integer', 'minimum': 1, 'default': self.default_limit},
            },
        ]

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'required': ['items', 'total'],
            'properties': {
                'items': schema,
                'total': {'type': 'integer', 'description': 'Сколько всего записей, без учёта пагинации'},
            },
        }

    @staticmethod
    def _positive_int(request, name, default):
        try:
            value = int(request.query_params.get(name, default))
        except ValueError:
            raise ValidationError({name: 'must be an integer'})
        if value < 1:
            raise ValidationError({name: 'must be >= 1'})
        return value

