from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services.access_tokens import AccessTokenService, InvalidAccessToken


class BearerAccessTokenAuthentication(BaseAuthentication):
    """`Authorization: Bearer <access JWT>`. No header -> anonymous; a bad token -> 401 even on public endpoints."""

    def authenticate(self, request):
        scheme, _, token = request.headers.get('Authorization', '').partition(' ')
        if scheme.lower() != 'bearer':
            return None
        try:
            user_id = AccessTokenService().verify(token.strip())
        except InvalidAccessToken:
            raise AuthenticationFailed('Invalid or expired access token', code='token_invalid')
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            raise AuthenticationFailed('User not found or inactive', code='user_inactive')
        return user, token

    def authenticate_header(self, request):
        return 'Bearer'  # makes DRF answer 401 (not 403) to unauthenticated requests
