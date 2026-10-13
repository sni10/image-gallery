from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.throttling import IPScopedRateThrottle

from ..services.complaints import ComplaintService
from .serializers import ComplaintSerializer


class ComplaintView(APIView):
    """Public: most complainants have no account. A token, if sent, links the complaint to the user."""

    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = 'complaint'
    complaints = ComplaintService()

    @extend_schema(
        summary='Жалоба на контент (письмо администрации)', request=ComplaintSerializer,
        responses={
            204: OpenApiResponse(description='Принята'),
            400: OpenApiResponse(description='Ошибки по полям email/photoUrl/message'),
            429: OpenApiResponse(description='Больше 5 жалоб в час с одного IP'),
        },
    )
    def post(self, request):
        serializer = ComplaintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.complaints.submit(
            email=data['email'], photo_url=data['photoUrl'], message=data['message'],
            ip=IPScopedRateThrottle().get_ident(request), user_agent=request.headers.get('User-Agent', ''),
            user=request.user if request.user.is_authenticated else None,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
