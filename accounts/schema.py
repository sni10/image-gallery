from drf_spectacular.extensions import OpenApiAuthenticationExtension


class BearerAccessTokenScheme(OpenApiAuthenticationExtension):
    """Describes BearerAccessTokenAuthentication in the OpenAPI schema (loaded from AccountsConfig.ready)."""

    target_class = 'accounts.authentication.BearerAccessTokenAuthentication'
    name = 'bearerAuth'

    def get_security_definition(self, auto_schema):
        return {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}
