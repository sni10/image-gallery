from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Gallery, Photo
from .permissions import HasIngestKey
from .serializers import GalleryTextSerializer, PhotoTextSerializer

RESPONSES = {
    204: OpenApiResponse(description='Сохранено'),
    400: OpenApiResponse(description='Ошибки по полям, например {"tags": ["..."]}'),
    403: OpenApiResponse(description='Нет или неверный X-Api-Key, либо ingest выключен на сервере'),
    404: OpenApiResponse(description='Нет такого объекта'),
}


@extend_schema(
    summary='Заменить тайтл, описание и теги фото (автоматизация)',
    description='Для custom/seo.py: тексты генерирует локальная LLM. Авторизация — `X-Api-Key` (INGEST_API_KEY). '
                'Меняются только переданные поля.',
    request=PhotoTextSerializer, responses=RESPONSES, auth=[],
)
class PhotoTextView(APIView):
    authentication_classes = []  # a stray Bearer header must not turn into a 401
    permission_classes = [HasIngestKey]

    def patch(self, request, photo_id):
        photo = get_object_or_404(Photo, public_id=photo_id)
        data = PhotoTextSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        for field, value in data.validated_data.items():
            setattr(photo, field, value)
        photo.save(update_fields=list(data.validated_data))
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    summary='Заменить SEO-текст галереи (автоматизация)',
    description='Для custom/seo.py. Авторизация — `X-Api-Key` (INGEST_API_KEY).',
    request=GalleryTextSerializer, responses=RESPONSES, auth=[],
)
class GalleryTextView(APIView):
    authentication_classes = []
    permission_classes = [HasIngestKey]

    def patch(self, request, id):
        gallery = get_object_or_404(Gallery, public_id=id)
        data = GalleryTextSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        gallery.description = data.validated_data['description']
        gallery.save(update_fields=['description'])
        return Response(status=status.HTTP_204_NO_CONTENT)
