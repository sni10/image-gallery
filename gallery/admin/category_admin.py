from django.contrib import admin
from django.db.models import Count

from ..models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'position', 'galleries_count']
    list_editable = ['position']
    prepopulated_fields = {'slug': ['title']}  # admin JS transliterates Cyrillic titles
    search_fields = ['title', 'slug']
    fields = ['title', 'slug', 'position']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(galleries_count=Count('galleries'))

    @admin.display(description='Галерей', ordering='galleries_count')
    def galleries_count(self, obj):
        return obj.galleries_count
