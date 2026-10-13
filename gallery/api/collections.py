from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Collection, Photo
from ..services import PhotoQueries
from ..services.collections import CollectionQueries, CollectionService, LimitReached
from .pagination import PageLimitPagination
from .serializers import CollectionSerializer, CollectionWithCoverSerializer, PhotoSerializer

UNAUTHORIZED = OpenApiResponse(description='Нет действующего access-токена')
NOT_FOUND = OpenApiResponse(description='Коллекции с таким id нет у текущего пользователя (чужие тоже 404)')
LIMIT = '{"detail": "...", "code": "limit"} — лимит: 100 коллекций на аккаунт или 1000 фото в коллекции'
COLLECTION_ID = OpenApiParameter('id', str, OpenApiParameter.PATH, description='Публичный id коллекции (поле id)')
PHOTO_ID = OpenApiParameter('photo_id', str, OpenApiParameter.PATH, description='Публичный id фото (поле id)')


def own_collection(request, collection_id) -> Collection:
    return get_object_or_404(CollectionQueries.of_user(request.user), public_id=collection_id)


def limit_error(exc: LimitReached) -> ValidationError:
    return ValidationError({'detail': str(exc), 'code': 'limit'})


class CollectionListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Мои коллекции',
        description='Сначала недавно изменённые (создание, переименование, добавление и удаление фото). Без пагинации.',
        parameters=[OpenApiParameter('photo', str, required=False,
                                     description='Публичный id фото: добавит в ответ hasPhoto для галочек')],
        responses={200: CollectionWithCoverSerializer(many=True), 401: UNAUTHORIZED},
    )
    def get(self, request):
        collections = CollectionQueries.of_user(request.user, request.query_params.get('photo'))
        collections = CollectionQueries.attach_covers(collections, request.user)
        return Response(CollectionWithCoverSerializer(collections, many=True, context={'request': request}).data)

    @extend_schema(
        summary='Создать коллекцию', request=CollectionSerializer,
        responses={201: CollectionWithCoverSerializer, 400: OpenApiResponse(description=f'Ошибка title или {LIMIT}'),
                   401: UNAUTHORIZED},
    )
    def post(self, request):
        data = CollectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            collection = CollectionService.create(request.user, data.validated_data['title'])
        except LimitReached as exc:
            raise limit_error(exc)
        return Response(_with_cover(request, collection.public_id), status=status.HTTP_201_CREATED)


class CollectionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Коллекция', parameters=[COLLECTION_ID],
                   responses={200: CollectionSerializer, 401: UNAUTHORIZED, 404: NOT_FOUND})
    def get(self, request, id):
        return Response(CollectionSerializer(own_collection(request, id)).data)

    @extend_schema(
        summary='Переименовать коллекцию', parameters=[COLLECTION_ID], request=CollectionSerializer,
        responses={200: CollectionWithCoverSerializer, 400: OpenApiResponse(description='Ошибка title'),
                   401: UNAUTHORIZED, 404: NOT_FOUND},
    )
    def patch(self, request, id):
        collection = own_collection(request, id)
        data = CollectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        CollectionService.rename(collection, data.validated_data['title'])
        return Response(_with_cover(request, id))

    @extend_schema(summary='Удалить коллекцию (фото остаются на сайте)', parameters=[COLLECTION_ID],
                   responses={204: OpenApiResponse(description='Удалена'), 401: UNAUTHORIZED, 404: NOT_FOUND})
    def delete(self, request, id):
        own_collection(request, id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    summary='Фото коллекции', description='Сначала недавно добавленные. Пагинация как у остальных списков.',
    parameters=[COLLECTION_ID],
    responses={200: PhotoSerializer(many=True), 400: OpenApiResponse(description='Неверный page/limit'),
               401: UNAUTHORIZED, 404: NOT_FOUND},
)
class CollectionPhotoListView(ListAPIView):
    serializer_class = PhotoSerializer
    pagination_class = PageLimitPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return Photo.objects.none()
        collection = own_collection(self.request, self.kwargs['id'])
        return PhotoQueries.for_user(CollectionQueries.photos(collection), self.request.user)


class CollectionPhotoView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Добавить фото в коллекцию', request=None, parameters=[COLLECTION_ID, PHOTO_ID],
        responses={204: OpenApiResponse(description='Добавлено (или уже было)'), 400: OpenApiResponse(description=LIMIT),
                   401: UNAUTHORIZED, 404: OpenApiResponse(description='Нет такой коллекции у пользователя или фото')},
    )
    def put(self, request, id, photo_id):
        try:
            CollectionService.add_photo(own_collection(request, id), photo_id)
        except Photo.DoesNotExist:
            raise NotFound('Photo not found.')
        except LimitReached as exc:
            raise limit_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Убрать фото из коллекции', parameters=[COLLECTION_ID, PHOTO_ID],
        responses={204: OpenApiResponse(description='Убрано (или его и не было)'), 401: UNAUTHORIZED, 404: NOT_FOUND},
    )
    def delete(self, request, id, photo_id):
        CollectionService.remove_photo(own_collection(request, id), photo_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _with_cover(request, collection_id):
    """The collection as GET /me/collections lists it (fresh counts and cover)."""
    [collection] = CollectionQueries.attach_covers(
        CollectionQueries.of_user(request.user).filter(public_id=collection_id), request.user)
    return CollectionWithCoverSerializer(collection, context={'request': request}).data
