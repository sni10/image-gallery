import django.db.models.deletion
import pgvector.django
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gallery', '0013_photo_search'),
    ]

    operations = [
        pgvector.django.VectorExtension(),  # needs the pgvector/pgvector Postgres image
        migrations.CreateModel(
            name='PhotoEmbedding',
            fields=[
                ('photo', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True,
                                               related_name='embedding', serialize=False, to='gallery.photo')),
                ('model', models.CharField(help_text='Имя модели, которой посчитан вектор', max_length=100)),
                ('vector', pgvector.django.VectorField(dimensions=768)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
