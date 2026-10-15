from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from ..models import Complaint, Photo


def _public_id(url):
    """photo_url is the site page (…/photos/<public_id>), the id is its last segment."""
    return url.rstrip('/').rsplit('/', 1)[-1]


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    # list is a grid of photo previews: admin/gallery/complaint/change_list.html
    list_display = ['created_at', 'email', 'photo_url', 'handled']
    list_filter = ['handled']
    list_per_page = 60
    search_fields = ['email', 'photo_url', 'message']
    actions = ['mark_handled', 'mark_unhandled']
    readonly_fields = ['photo_preview', 'email_link', 'message', 'ip', 'user_agent', 'user', 'created_at']
    fieldsets = [
        ('Фото', {'fields': ['photo_preview']}),
        ('Жалоба', {'fields': ['message', 'handled', 'created_at']}),
        ('Отправитель', {'fields': ['email_link', 'user', 'ip', 'user_agent']}),
    ]

    def get_changelist_instance(self, request):
        changelist = super().get_changelist_instance(request)
        complaints = changelist.result_list
        ids = {_public_id(c.photo_url) for c in complaints if c.photo_url}
        photos = {p.public_id: p for p in Photo.objects.filter(public_id__in=ids)}
        for c in complaints:
            c.photo = photos.get(_public_id(c.photo_url)) if c.photo_url else None
        return changelist

    @admin.display(description='Фото')
    def photo_preview(self, obj):
        if not obj.photo_url:
            return 'без ссылки'
        photo = Photo.objects.filter(public_id=_public_id(obj.photo_url)).first()
        if not photo:
            return format_html('Фото не найдено (удалено?): <a href="{0}" target="_blank">{0}</a>', obj.photo_url)
        gallery_url = reverse('admin:gallery_gallery_change', args=[photo.gallery_id])
        return format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-width:100%;max-height:60vh;border-radius:6px"></a>'
            '<p>«{}» · <a href="{}" target="_blank">на сайте</a> · <a href="{}">галерея «{}» в админке</a></p>',
            photo.image.url, photo.image.url, photo.title, obj.photo_url, gallery_url, photo.gallery,
        )

    @admin.display(description='Email')
    def email_link(self, obj):
        return format_html('<a href="mailto:{0}">{0}</a>', obj.email)

    @admin.action(description='Отметить обработанными')
    def mark_handled(self, request, queryset):
        queryset.update(handled=True)

    @admin.action(description='Снять отметку «обработана»')
    def mark_unhandled(self, request, queryset):
        queryset.update(handled=False)
