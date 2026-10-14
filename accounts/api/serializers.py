from django.conf import settings
from rest_framework import serializers

MUST_ACCEPT = 'You must accept the Terms of Use.'
TERMS_CHANGED = 'The Terms of Use have changed, reload the page.'


class RegisterSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254, help_text='Регистр и пробелы по краям не важны')
    password = serializers.CharField(write_only=True, trim_whitespace=False,
                                     help_text='Не короче 8 символов, не распространённый, не только цифры')
    termsAccepted = serializers.BooleanField(
        help_text='Согласие с Правилами использования (/terms), должно быть true',
        error_messages={'required': MUST_ACCEPT, 'null': MUST_ACCEPT, 'invalid': MUST_ACCEPT},
    )
    termsVersion = serializers.CharField(
        max_length=10, help_text='Редакция Правил, которую видел пользователь (YYYY-MM-DD); должна быть текущей',
        error_messages={'required': TERMS_CHANGED, 'blank': TERMS_CHANGED, 'max_length': TERMS_CHANGED},
    )

    def validate_termsAccepted(self, value):
        if not value:
            raise serializers.ValidationError(MUST_ACCEPT)
        return value

    def validate_termsVersion(self, value):
        if value != settings.TERMS_VERSION:
            raise serializers.ValidationError(TERMS_CHANGED)
        return value


class RegisteredSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text='Нормализованный email; на него отправлено письмо подтверждения')


class EmailSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(help_text='Токен из ссылки в письме')


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254, help_text='Регистр и пробелы по краям не важны')


class PasswordResetConfirmSerializer(TokenSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False,
                                     help_text='Новый пароль: те же правила, что при регистрации')


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class MeSerializer(serializers.Serializer):
    id = serializers.CharField(source='profile.public_id', help_text='Публичный id: 26 символов [a-z2-7], не число')
    email = serializers.EmailField()
    dateJoined = serializers.DateTimeField(source='date_joined')
    isAdmin = serializers.BooleanField(source='is_staff', help_text='Может удалять фото: DELETE /photos/{photo_id}')


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, help_text='Текущий пароль')


class ChangeEmailSerializer(serializers.Serializer):
    newEmail = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, help_text='Текущий пароль')


class ChangedEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text='Новый email, теперь это логин')


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(write_only=True, trim_whitespace=False)
    newPassword = serializers.CharField(write_only=True, trim_whitespace=False)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(help_text='JWT для заголовка `Authorization: Bearer`, живёт 15 минут')
    refresh = serializers.CharField(help_text='Для POST /auth/refresh, живёт 7 дней, одноразовый')
