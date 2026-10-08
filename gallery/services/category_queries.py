from django.db.models import Count, QuerySet

from ..models import Category


class CategoryQueries:
    """Read-side queries for categories."""

    @staticmethod
    def non_empty() -> QuerySet[Category]:
        """Categories with at least one gallery, annotated with `galleries_count`, in display order."""
        return (
            Category.objects.annotate(galleries_count=Count('galleries'))
            .filter(galleries_count__gt=0)
            .order_by('position', 'title')
        )
