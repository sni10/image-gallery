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
        offset = (page - 1) * limit
        return list(queryset[offset:offset + limit])

    def get_paginated_response(self, data):
        return Response({'items': data, 'total': self.total})

    @staticmethod
    def _positive_int(request, name, default):
        try:
            value = int(request.query_params.get(name, default))
        except ValueError:
            raise ValidationError({name: 'must be an integer'})
        if value < 1:
            raise ValidationError({name: 'must be >= 1'})
        return value
