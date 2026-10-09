from django.contrib import admin


class ReissueLinkAdminMixin:
    """Admin action for PublicIdModel: new link date = now -> new public id, the old link returns 404."""

    @admin.action(description='Перевыпустить ссылку (новый публичный id, старая ссылка перестанет работать)')
    def reissue_links(self, request, queryset):
        for obj in queryset:
            obj.reissue_link()
        self.message_user(request, f'Ссылки перевыпущены: {len(queryset)}')
