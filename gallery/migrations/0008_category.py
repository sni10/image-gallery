# Galleries become required to have a category. Existing galleries are not migrated: the gallery data is wiped
# and re-uploaded (decided when adding categories), so on a database that still has galleries this migration fails.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gallery', '0007_favorite'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100)),
                ('slug', models.SlugField(help_text='Для адреса: латиница, цифры, дефис (например ai, comics)', unique=True)),
                ('position', models.IntegerField(default=0, help_text='Порядок в списке категорий: меньше — выше')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'categories',
                'ordering': ['position', 'title'],
            },
        ),
        migrations.AddField(
            model_name='gallery',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='galleries', to='gallery.category',
                verbose_name='Категория',
            ),
            preserve_default=False,
        ),
    ]
