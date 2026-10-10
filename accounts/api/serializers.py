from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254, help_text='Регистр и пробелы по краям не важны')
    password = serializers.CharField(write_only=True, trim_whitespace=False,
                                     help_text='Не короче 8 символов, не распространённый, не только цифры')


class RegisteredSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text='Нормализованный email; на него отправлено письмо подтверждения')


class EmailSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(help_text='Токен из ссылки в письме')


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
