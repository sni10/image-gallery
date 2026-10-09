from django.db import models
from django.utils import timezone

from .public_ids import make_public_id


class PublicIdModel(models.Model):
    """Adds a public id that hides the database pk, and the "link date" it is derived from.

    The id is stored (lookups need an index; there is no way back from the hash) and recomputed only when
    `link_date` changes, so rotating SECRET_KEY does not break already published links. Both columns are
    nullable in the DB only because the hash needs the pk, which exists after the insert; `save()` always
    fills them.
    """

    link_date = models.DateTimeField(
        'Дата ссылки', null=True, blank=True,
        help_text='Из неё вычисляется публичный id. Смена даты выдаёт новый id, старая ссылка перестаёт работать. '
                  'Пусто — дата создания.',
    )
    public_id = models.CharField(max_length=26, unique=True, null=True, editable=False)

    class Meta:
        abstract = True

    def default_link_date(self):
        return self.created_at

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._stored_link_date = instance.__dict__.get('link_date')
        return instance

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        link_date = self.link_date or self.default_link_date()
        if self.public_id and link_date == getattr(self, '_stored_link_date', None):
            return
        self.link_date = link_date
        self.public_id = make_public_id(self._meta.label_lower, self.pk, link_date)
        type(self)._base_manager.filter(pk=self.pk).update(link_date=self.link_date, public_id=self.public_id)
        self._stored_link_date = link_date

    def reissue_link(self) -> None:
        """New link date = now -> new public id; the old one stops resolving."""
        self.link_date = timezone.now()
        self.save()
