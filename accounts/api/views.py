from dataclasses import asdict

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ..services.auth import AuthService, EmailNotConfirmed, InvalidCredentials
from ..services.email_tokens import InvalidEmailToken
from ..services.password_reset import PasswordResetService
from ..services.profile import AdminAccountProtected, ProfileService
from ..services.registration import RegistrationService
from ..services.token_pairs import InvalidRefreshToken
from ..throttling import EmailScopedRateThrottle, IPScopedRateThrottle
from .serializers import (
    ChangedEmailSerializer, ChangeEmailSerializer, ChangePasswordSerializer, EmailSerializer, LoginSerializer,
    MeSerializer, PasswordResetConfirmSerializer, PasswordResetSerializer, PasswordSerializer, RefreshSerializer,
    RegisteredSerializer, RegisterSerializer, TokenPairSerializer, TokenSerializer,
)

UNAUTHORIZED = OpenApiResponse(description='Нет действующего access-токена')
THROTTLED = OpenApiResponse(description='Больше 10 запросов в минуту с одного IP')

BAD_LINK = 'The link is invalid or has expired.'


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def api_fields(exc: DjangoValidationError, names: dict) -> ValidationError:
    """Rename service error keys (snake_case arguments) to the request's camelCase fields."""
    return ValidationError({names.get(key, key): messages for key, messages in exc.message_dict.items()})


class AuthThrottled(APIView):
    """Base for auth endpoints: 10 requests/min per IP for the view's `throttle_scope`."""

    throttle_classes = [IPScopedRateThrottle]


class RegisterView(AuthThrottled):
    throttle_scope = 'register'
    registration = RegistrationService()

    @extend_schema(
        summary='Регистрация', request=RegisterSerializer,
        responses={429: THROTTLED, 201: RegisteredSerializer,
                   400: OpenApiResponse(description='Ошибки по полям email/password/termsAccepted/termsVersion')},
    )
    def post(self, request):
        data = validated(RegisterSerializer, request)  # terms are checked here, before the account and the email
        user = self.registration.register(data['email'], data['password'], data['termsVersion'])
        return Response({'email': user.email}, status=status.HTTP_201_CREATED)


class ConfirmEmailView(AuthThrottled):
    throttle_scope = 'confirm_email'
    registration = RegistrationService()

    @extend_schema(
        summary='Подтверждение email по ссылке из письма', request=TokenSerializer,
        responses={429: THROTTLED, 200: TokenPairSerializer, 400: OpenApiResponse(description='Ссылка недействительна или устарела')},
    )
    def post(self, request):
        try:
            pair = self.registration.confirm(validated(TokenSerializer, request)['token'])
        except InvalidEmailToken:
            raise ValidationError({'token': [BAD_LINK]})
        return Response(asdict(pair))


class ResendConfirmationView(AuthThrottled):
    throttle_scope = 'resend_confirmation'
    registration = RegistrationService()

    @extend_schema(
        summary='Повторно отправить письмо подтверждения', request=EmailSerializer,
        responses={429: THROTTLED, 204: OpenApiResponse(description='Всегда, даже если аккаунта нет — не раскрывает, кто зарегистрирован')},
    )
    def post(self, request):
        self.registration.resend_confirmation(validated(EmailSerializer, request)['email'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    throttle_classes = [IPScopedRateThrottle, EmailScopedRateThrottle]
    throttle_scope = 'password_reset'
    passwords = PasswordResetService()

    @extend_schema(
        summary='Забыли пароль: прислать ссылку для сброса', request=PasswordResetSerializer,
        responses={
            204: OpenApiResponse(description='Всегда, даже если аккаунта нет — не раскрывает, кто зарегистрирован. '
                                             'Письмо со ссылкой {FRONTEND_URL}/reset-password?token=…, живёт 1 час'),
            400: OpenApiResponse(description='email не похож на адрес: {"email": ["..."]}'),
            429: OpenApiResponse(description='Больше 5 запросов в час с одного IP или на один email'),
        },
    )
    def post(self, request):
        self.passwords.request(validated(PasswordResetSerializer, request)['email'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(AuthThrottled):
    throttle_scope = 'password_reset_confirm'
    passwords = PasswordResetService()

    @extend_schema(
        summary='Задать новый пароль по ссылке из письма', request=PasswordResetConfirmSerializer,
        responses={
            429: THROTTLED,
            200: OpenApiResponse(TokenPairSerializer, description='Пароль сменён, пользователь вошёл; все прежние '
                                                                  'refresh-токены отозваны, email считается подтверждённым'),
            400: OpenApiResponse(description='{"token": ["..."]} — ссылка недействительна, устарела или уже '
                                             'использована; {"password": ["..."]} — слабый пароль, ссылка остаётся рабочей'),
        },
    )
    def post(self, request):
        data = validated(PasswordResetConfirmSerializer, request)
        try:
            pair = self.passwords.confirm(data['token'], data['password'])
        except InvalidEmailToken:
            raise ValidationError({'token': [BAD_LINK]})
        except DjangoValidationError as exc:
            raise api_fields(exc, {})
        return Response(asdict(pair))


class LoginView(AuthThrottled):
    throttle_scope = 'login'
    auth = AuthService()

    @extend_schema(
        summary='Вход', request=LoginSerializer,
        responses={429: THROTTLED, 
            200: TokenPairSerializer,
            401: OpenApiResponse(description='Неверный email или пароль (одинаково для обоих случаев)'),
            403: OpenApiResponse(description='{"detail": "...", "code": "email_not_confirmed"}'),
        },
    )
    def post(self, request):
        data = validated(LoginSerializer, request)
        try:
            pair = self.auth.login(data['email'], data['password'])
        except InvalidCredentials:
            raise AuthenticationFailed('Invalid email or password.')
        except EmailNotConfirmed:
            raise PermissionDenied({'detail': 'Email is not confirmed.', 'code': 'email_not_confirmed'})
        return Response(asdict(pair))


class RefreshView(APIView):
    auth = AuthService()

    @extend_schema(
        summary='Обновить пару токенов', request=RefreshSerializer,
        responses={200: TokenPairSerializer, 401: OpenApiResponse(description='Refresh просрочен, отозван или подделан')},
    )
    def post(self, request):
        try:
            pair = self.auth.refresh(validated(RefreshSerializer, request)['refresh'])
        except InvalidRefreshToken:
            raise AuthenticationFailed('Invalid refresh token.')
        return Response(asdict(pair))


class LogoutView(APIView):
    auth = AuthService()

    @extend_schema(summary='Выход: отзыв refresh-токена', request=RefreshSerializer,
                   responses={204: OpenApiResponse(description='Токен отозван')})
    def post(self, request):
        self.auth.logout(validated(RefreshSerializer, request)['refresh'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'delete_account'
    profile = ProfileService()

    def get_throttles(self):  # only DELETE checks a password
        return [IPScopedRateThrottle()] if self.request.method == 'DELETE' else []

    @extend_schema(summary='Текущий пользователь', responses={200: MeSerializer, 401: UNAUTHORIZED})
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(
        summary='Удалить аккаунт', request=PasswordSerializer,
        responses={
            204: OpenApiResponse(description='Удалены аккаунт, профиль, сессии и избранное; жалобы остаются без связи'),
            400: OpenApiResponse(description='{"password": ["Wrong password."]}'),
            401: UNAUTHORIZED,
            403: OpenApiResponse(description='Аккаунт администратора так не удалить'),
            429: THROTTLED,
        },
    )
    def delete(self, request):
        try:
            self.profile.delete_account(request.user, validated(PasswordSerializer, request)['password'])
        except AdminAccountProtected:
            raise PermissionDenied('Admin accounts cannot be deleted here.')
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangeEmailView(APIView):
    permission_classes = [IsAuthenticated]
    profile = ProfileService()

    @extend_schema(
        summary='Запросить смену email', request=ChangeEmailSerializer,
        responses={
            202: OpenApiResponse(description='Письмо со ссылкой отправлено на новый адрес; email пока прежний'),
            400: OpenApiResponse(description='Ошибки по полям newEmail/password'),
            401: UNAUTHORIZED,
        },
    )
    def post(self, request):
        data = validated(ChangeEmailSerializer, request)
        try:
            self.profile.request_email_change(request.user, data['newEmail'], data['password'])
        except DjangoValidationError as exc:
            raise api_fields(exc, {'new_email': 'newEmail'})
        return Response(status=status.HTTP_202_ACCEPTED)


class ConfirmEmailChangeView(APIView):
    profile = ProfileService()

    @extend_schema(
        summary='Подтвердить смену email по ссылке из письма', request=TokenSerializer,
        responses={200: ChangedEmailSerializer,
                   400: OpenApiResponse(description='Ссылка недействительна, устарела или адрес уже занят')},
    )
    def post(self, request):
        try:
            email = self.profile.confirm_email_change(validated(TokenSerializer, request)['token'])
        except InvalidEmailToken:
            raise ValidationError({'token': [BAD_LINK]})
        return Response({'email': email})


class ChangePasswordView(AuthThrottled):
    throttle_scope = 'change_password'
    permission_classes = [IsAuthenticated]
    profile = ProfileService()

    @extend_schema(
        summary='Сменить пароль', request=ChangePasswordSerializer,
        responses={429: THROTTLED, 
            200: OpenApiResponse(TokenPairSerializer, description='Новая пара; все прежние refresh-токены отозваны'),
            400: OpenApiResponse(description='Ошибки по полям currentPassword/newPassword'),
            401: UNAUTHORIZED,
        },
    )
    def post(self, request):
        data = validated(ChangePasswordSerializer, request)
        try:
            pair = self.profile.change_password(request.user, data['currentPassword'], data['newPassword'])
        except DjangoValidationError as exc:
            raise api_fields(exc, {'current_password': 'currentPassword', 'new_password': 'newPassword'})
        return Response(asdict(pair))
