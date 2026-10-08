# Separate from 0003: PostgreSQL can't ALTER a table with pending FK trigger events from the data update.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('gallery', '0003_gallery_photo_gallery'),
    ]

    operations = [
        migrations.AlterField(
            model_name='photo',
            name='gallery',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='gallery.gallery',
            ),
        ),
    ]
