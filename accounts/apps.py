from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        from . import schema, signals  # noqa: F401  register the OpenAPI auth extension and signals
