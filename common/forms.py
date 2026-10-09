from django import forms


class LinkDateFormMixin:
    """For ModelForms of PublicIdModel. Admin widgets drop microseconds, so saving an untouched form would
    write a slightly different link date and silently reissue the public id. Keep the stored value unless
    the field was actually edited (`changed_data` compares at the widget's precision)."""

    def clean(self):
        data = super().clean()
        if self.instance.pk and 'link_date' in data and 'link_date' not in self.changed_data:
            data['link_date'] = self.instance.link_date
        return data


class PublicIdModelForm(LinkDateFormMixin, forms.ModelForm):
    pass
