from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gallery', '0014_photoembedding'),
    ]

    operations = [
        migrations.AddField(
            model_name='gallery',
            name='description',
            field=models.TextField(blank=True, default='', help_text='SEO-текст страницы галереи'),
        ),
    ]
