from pathlib import Path

from django.contrib import admin
from django.utils.html import format_html

from ..models import Gallery
from ..services import GalleryQueries, PhotoService
from .forms import GalleryAdminForm


@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    form = GalleryAdminForm
    fields = ['title', 'category', 'new_images']  # the photo grid is rendered by the change_form template
    list_display = ['id', 'cover_preview', 'title', 'category', 'photos_count', 'created_at']
    list_display_links = ['id', 'cover_preview', 'title']
    list_filter = ['category']
    search_fields = ['title']
    photo_service = PhotoService()

    def get_queryset(self, request):
        return GalleryQueries.with_stats()

    def get_changelist_instance(self, request):
        changelist = super().get_changelist_instance(request)
        GalleryQueries.attach_covers(changelist.result_list, request.user)
        return changelist

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        obj.cover = data['cover']
        super().save_model(request, obj, form, change)

        files = data['new_images']
        for f in files:
            self.photo_service.create(f, obj, title=Path(f.name).stem)
        if files:
            self.message_user(request, f'Загружено фото: {len(files)}')

        selected = data['selected']
        if data['move_to']:
            moved = self.photo_service.move(selected, data['move_to'])
            self.message_user(request, f'Перенесено фото в «{data["move_to"]}»: {moved}')
        elif data['delete_selected']:
            deleted = self.photo_service.delete(selected)
            self.message_user(request, f'Удалено фото: {deleted}')

    @admin.display(description='Обложка')
    def cover_preview(self, obj):
        cover = getattr(obj, 'display_cover', None)
        if not cover:
            return 'нет фото'
        note = '' if cover.pk == obj.cover_id else 'случайная'
        return format_html('<img src="{}" style="height:60px"><br><small>{}</small>', cover.thumb.url, note)

    @admin.display(description='Фото', ordering='photos_count')
    def photos_count(self, obj):
        return obj.photos_count
