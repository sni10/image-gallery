from django.contrib import admin
from django.db.models import Count

from common.admin_mixins import ReissueLinkAdminMixin
from common.forms import PublicIdModelForm

from ..models import Category


@admin.register(Category)
class CategoryAdmin(ReissueLinkAdminMixin, admin.ModelAdmin):
    form = PublicIdModelForm
    list_display = ['title', 'slug', 'position', 'galleries_count']
    list_editable = ['position']
    prepopulated_fields = {'slug': ['title']}  # admin JS transliterates Cyrillic titles
    search_fields = ['title', 'slug']
    fields = ['title', 'slug', 'position', 'link_date', 'public_id']
    readonly_fields = ['public_id']
    actions = ['reissue_links']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(galleries_count=Count('galleries'))

    @admin.display(description='Галерей', ordering='galleries_count')
    def galleries_count(self, obj):
        return obj.galleries_count
