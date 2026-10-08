from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserver


class Command(StaticfilesRunserver):
    """`runserver` whose default address comes from APP_HOST / APP_PORT."""

    default_addr = settings.APP_HOST
    default_port = str(settings.APP_PORT)
