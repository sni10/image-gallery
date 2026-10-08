import django.db.models.deletion
from django.db import migrations, models

DEFAULT_GALLERY_TITLE = 'Без галереи'


def move_existing_photos(apps, schema_editor):
    Gallery = apps.get_model('gallery', 'Gallery')
    Photo = apps.get_model('gallery', 'Photo')
    if Photo.objects.exists():
        default = Gallery.objects.create(title=DEFAULT_GALLERY_TITLE)
        Photo.objects.update(gallery=default)


class Migration(migrations.Migration):
    dependencies = [
        ('gallery', '0002_alter_photo_image_alter_photo_title'),
    ]

    operations = [
        migrations.CreateModel(
            name='Gallery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-id'], 'verbose_name_plural': 'galleries'},
        ),
        migrations.AddField(
            model_name='photo',
            name='gallery',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='gallery.gallery',
            ),
        ),
        migrations.RunPython(move_existing_photos, migrations.RunPython.noop),
    ]
