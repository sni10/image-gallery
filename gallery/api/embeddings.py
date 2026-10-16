from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Photo, PhotoEmbedding
from .permissions import HasIngestKey
from .serializers import EmbeddingBatchSerializer


@extend_schema(
    summary='Сохранить векторы фото (автоматизация)',
    description='Для custom/embed.py: векторы считаются не на сервере. Авторизация — `X-Api-Key` (INGEST_API_KEY), '
                'как у POST /ingest/photos. Вектор фото перезаписывается, в том числе вектор другой модели. '
                'Фото, которых нет (удалены), пропускаются и перечислены в `unknown`.',
    request=EmbeddingBatchSerializer,
    responses={
        200: inline_serializer('SavedEmbeddings', {
            'saved': serializers.IntegerField(), 'unknown': serializers.ListField(child=serializers.CharField()),
        }),
        400: OpenApiResponse(description='Ошибки по полям, например {"items": [{"vector": ["..."]}]}'),
        403: OpenApiResponse(description='Нет или неверный X-Api-Key, либо ingest выключен на сервере'),
    },
    auth=[],
)
class EmbeddingView(APIView):
    authentication_classes = []  # a stray Bearer header must not turn into a 401
    permission_classes = [HasIngestKey]

    def post(self, request):
        data = EmbeddingBatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        model, items = data.validated_data['model'], data.validated_data['items']
        pks = dict(Photo.objects.filter(public_id__in=[i['id'] for i in items]).values_list('public_id', 'pk'))
        rows = [PhotoEmbedding(photo_id=pks[i['id']], model=model, vector=i['vector']) for i in items if i['id'] in pks]
        PhotoEmbedding.objects.bulk_create(rows, update_conflicts=True, unique_fields=['photo'],
                                           update_fields=['model', 'vector', 'updated_at'])
        return Response({'saved': len(rows), 'unknown': [i['id'] for i in items if i['id'] not in pks]})
