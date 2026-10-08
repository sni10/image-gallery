from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """Services raise Django's ValidationError (they don't depend on DRF); answer it with 400 like DRF's own."""
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, 'error_dict') else exc.messages)
    return drf_exception_handler(exc, context)
