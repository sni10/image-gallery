from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Photo, PhotoEmbedding
from .permissions import HasIngestKey
from .serializers import EmbeddingBatchSerializer

NO_KEY = OpenApiResponse(description='Нет или неверный X-Api-Key, либо ingest выключен на сервере')


class EmbeddingView(APIView):
    """Vectors are computed off-server by embed_photos.py (repo root): it asks what is missing, downloads the
    thumbnails, sends the vectors back. Same X-Api-Key as POST /ingest/photos."""

    authentication_classes = []  # a stray Bearer header must not turn into a 401
    permission_classes = [HasIngestKey]

    @extend_schema(
        summary='Фото без вектора (автоматизация)',
        description='Все фото, у которых нет вектора модели `model`, одним списком, без пагинации. '
                    'thumbUrl — превью WebP до 400px, его и прогонять через модель.',
        parameters=[OpenApiParameter('model', str, required=True, description='Имя модели, как в POST')],
        responses={
            200: inline_serializer('MissingEmbeddings', {'items': inline_serializer('MissingEmbedding', {
                'id': serializers.CharField(), 'thumbUrl': serializers.URLField(),
            }, many=True)}),
            400: OpenApiResponse(description='Нет model'),
            403: NO_KEY,
        },
        auth=[],
    )
    def get(self, request):
        model = request.query_params.get('model', '').strip()
        if not model:
            raise ValidationError({'model': ['This parameter is required.']})
        photos = (Photo.objects.exclude(thumb='').exclude(embedding__model=model)
                  .order_by('pk').values_list('public_id', 'thumb'))
        storage = Photo._meta.get_field('thumb').storage
        return Response({'items': [{'id': public_id, 'thumbUrl': request.build_absolute_uri(storage.url(thumb))}
                                   for public_id, thumb in photos]})

    @extend_schema(
        summary='Сохранить векторы (автоматизация)',
        description='Вектор фото перезаписывается, в том числе вектор другой модели. Фото, которых уже нет '
                    '(удалены после GET), пропускаются и перечислены в `unknown`.',
        request=EmbeddingBatchSerializer,
        responses={
            200: inline_serializer('SavedEmbeddings', {
                'saved': serializers.IntegerField(), 'unknown': serializers.ListField(child=serializers.CharField()),
            }),
            400: OpenApiResponse(description='Ошибки по полям, например {"items": [{"vector": ["..."]}]}'),
            403: NO_KEY,
        },
        auth=[],
    )
    def post(self, request):
        data = EmbeddingBatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        model, items = data.validated_data['model'], data.validated_data['items']
        pks = dict(Photo.objects.filter(public_id__in=[i['id'] for i in items]).values_list('public_id', 'pk'))
        rows = [PhotoEmbedding(photo_id=pks[i['id']], model=model, vector=i['vector']) for i in items if i['id'] in pks]
        PhotoEmbedding.objects.bulk_create(rows, update_conflicts=True, unique_fields=['photo'],
                                           update_fields=['model', 'vector', 'updated_at'])
        return Response({'saved': len(rows), 'unknown': [i['id'] for i in items if i['id'] not in pks]})
