from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from common.forms import PublicIdModelForm

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    form = PublicIdModelForm
    can_delete = False
    fields = ['link_date', 'public_id', 'terms_version', 'terms_accepted_at']
    readonly_fields = ['public_id', 'terms_version', 'terms_accepted_at']
    verbose_name_plural = 'Публичная ссылка'


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class UserWithProfileAdmin(UserAdmin):
    inlines = [ProfileInline]
    actions = ['reissue_links']

    def get_inline_instances(self, request, obj=None):
        return super().get_inline_instances(request, obj) if obj else []  # the profile is created by a signal

    @admin.action(description='Перевыпустить ссылку (новый публичный id; старые access-токены и ссылки из писем '
                              'перестанут работать)')
    def reissue_links(self, request, queryset):
        for user in queryset.select_related('profile'):
            user.profile.reissue_link()
        self.message_user(request, f'Ссылки перевыпущены: {len(queryset)}')
