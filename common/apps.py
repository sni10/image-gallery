from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Shared building blocks for other apps; has no tables of its own."""

    name = 'common'
