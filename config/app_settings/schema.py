"""Typed configuration sections. Each section reads env vars with its own prefix and validates them."""
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Port = Annotated[int, Field(ge=1, le=65535)]
CommaList = Annotated[list[str], NoDecode]  # "a, b" in env -> ['a', 'b']


def split_commas(value):
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return value


class Section(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore', env_file_encoding='utf-8')


class DjangoSettings(Section):
    model_config = SettingsConfigDict(env_prefix='DJANGO_')

    secret_key: SecretStr
    debug: bool = False
    allowed_hosts: CommaList = []

    _split_hosts = field_validator('allowed_hosts', mode='before')(split_commas)

    @model_validator(mode='after')
    def check_production(self):
        if self.debug:
            return self
        key = self.secret_key.get_secret_value()
        if len(key) < 50 or key.startswith('django-insecure-'):
            raise ValueError('DJANGO_SECRET_KEY must be a random value of 50+ chars when DJANGO_DEBUG=false')
        if not self.allowed_hosts:
            raise ValueError('DJANGO_ALLOWED_HOSTS is required when DJANGO_DEBUG=false')
        return self


class DatabaseSettings(Section):
    model_config = SettingsConfigDict(env_prefix='DB_')

    name: str
    user: str
    password: SecretStr
    host: str = 'localhost'
    port: Port = 5432


class ServerSettings(Section):
    """Default address for `manage.py runserver`."""

    model_config = SettingsConfigDict(env_prefix='APP_')

    host: str = '127.0.0.1'
    port: Port = 8000


class CorsSettings(Section):
    model_config = SettingsConfigDict(env_prefix='CORS_')

    allowed_origins: CommaList = []

    _split_origins = field_validator('allowed_origins', mode='before')(split_commas)

    @field_validator('allowed_origins')
    @classmethod
    def check_origins(cls, origins):
        for origin in origins:
            parts = urlsplit(origin)
            if parts.scheme not in ('http', 'https') or not parts.netloc or parts.path or parts.query:
                raise ValueError(f'"{origin}" must look like scheme://host[:port] without a path')
        return origins


class MediaSettings(Section):
    model_config = SettingsConfigDict(env_prefix='MEDIA_')

    root: Path = Path('media')  # relative paths are resolved against the project root
    url: str = 'media/'

    @field_validator('url')
    @classmethod
    def check_url(cls, url):
        if not url.endswith('/'):
            raise ValueError('must end with "/"')
        return url


class StaticSettings(Section):
    model_config = SettingsConfigDict(env_prefix='STATIC_')

    root: Path = Path('staticfiles')  # `collectstatic` target served by nginx; relative to the project root


class AppSettings(BaseModel):
    django: DjangoSettings
    db: DatabaseSettings
    server: ServerSettings
    cors: CorsSettings
    media: MediaSettings
    static: StaticSettings
