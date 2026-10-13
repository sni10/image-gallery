from django.contrib import admin

from ..models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'email', 'photo_url', 'handled']
    list_editable = ['handled']
    list_filter = ['handled']
    search_fields = ['email', 'photo_url', 'message']
    readonly_fields = ['email', 'photo_url', 'message', 'ip', 'user_agent', 'user', 'created_at']
