from django import forms

from common.forms import LinkDateFormMixin

from ..models import Gallery, Photo
from ..services import SUPPORTED_FORMATS


class MultipleImageInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data and self.required:
            raise forms.ValidationError(self.error_messages['required'], code='required')
        files = [super(MultipleImageField, self).clean(f, initial) for f in data or []]
        for f in files:
            if f.image.format not in SUPPORTED_FORMATS:  # f.image is set by ImageField validation
                raise forms.ValidationError(
                    f'{f.name}: формат {f.image.format} не поддерживается, '
                    f'можно {", ".join(SUPPORTED_FORMATS)}'
                )
        return files


class GalleryAdminForm(LinkDateFormMixin, forms.ModelForm):
    """Gallery edit form. Besides the title it uploads new photos and handles the photo grid:
    `cover` (radio per photo) and `selected` (checkbox per photo) + what to do with the selection.
    The grid is rendered by admin/gallery/gallery/change_form.html."""

    new_images = MultipleImageField(
        label='Загрузить фото', required=False, help_text='Можно выбрать сразу несколько файлов',
    )
    cover = forms.ModelChoiceField(Photo.objects.none(), required=False)
    selected = forms.ModelMultipleChoiceField(Photo.objects.none(), required=False)
    move_to = forms.ModelChoiceField(Gallery.objects.none(), required=False, label='Перенести в галерею')
    delete_selected = forms.BooleanField(required=False, label='Удалить')
    reissue_selected = forms.BooleanField(required=False, label='Перевыпустить ссылки')

    class Meta:
        model = Gallery
        fields = ['title', 'category', 'link_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ponytail: renders every photo of the gallery; paginate the grid if galleries reach thousands
        self.photos = self.instance.photos.all() if self.instance.pk else Photo.objects.none()
        self.fields['cover'].queryset = self.photos
        self.fields['selected'].queryset = self.photos
        self.fields['move_to'].queryset = Gallery.objects.exclude(pk=self.instance.pk)
        self.initial.setdefault('cover', self.instance.cover_id)

    def clean(self):
        data = super().clean()
        chosen = [bool(data.get(name)) for name in ('move_to', 'delete_selected', 'reissue_selected')]
        if sum(chosen) > 1:
            raise forms.ValidationError('Выберите что-то одно: перенести, удалить или перевыпустить ссылки')
        if any(chosen) and not data.get('selected'):
            raise forms.ValidationError('Отметьте фото галочкой «выбрать»')
        return data
