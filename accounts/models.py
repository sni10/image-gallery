from django.conf import settings
from django.db import models

from common.models import PublicIdModel


class RefreshToken(models.Model):
    """Opaque refresh token. Only its SHA-256 is stored; the raw value lives on the client."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='refresh_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    family = models.UUIDField(db_index=True, help_text='Chain of tokens produced by rotation from one login')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    rotated = models.BooleanField(default=False, help_text='Revoked because it was exchanged for a new pair')

    def __str__(self):
        return f'{self.user} / {self.family}'


class Profile(PublicIdModel):
    """The user's public id (auth.User can't get fields of its own). Created automatically with the user."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    terms_version = models.CharField('Редакция Правил', max_length=10, blank=True,
                                     help_text='Пусто — регистрировался до появления Правил')
    terms_accepted_at = models.DateTimeField('Правила приняты', null=True, blank=True)

    def __str__(self):
        return str(self.user)

    def default_link_date(self):
        return self.user.date_joined
