from rest_framework import serializers

from ..models import Gallery, Photo


class PhotoSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    url = serializers.SerializerMethodField()
    thumbUrl = serializers.SerializerMethodField(method_name='get_thumb_url')

    class Meta:
        model = Photo
        fields = ['id', 'title', 'url', 'thumbUrl', 'width', 'height']

    def get_url(self, obj):
        return self._absolute(obj.image)

    def get_thumb_url(self, obj):
        return self._absolute(obj.thumb or obj.image)

    def _absolute(self, file):
        return self.context['request'].build_absolute_uri(file.url)


class GallerySerializer(serializers.ModelSerializer):
    """Expects galleries from GalleryQueries.with_stats() with covers attached."""

    id = serializers.CharField(read_only=True)
    photosCount = serializers.IntegerField(source='photos_count', read_only=True)
    cover = PhotoSerializer(source='display_cover', read_only=True, allow_null=True)

    class Meta:
        model = Gallery
        fields = ['id', 'title', 'photosCount', 'cover']
