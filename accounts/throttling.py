from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class IPScopedRateThrottle(ScopedRateThrottle):
    """ScopedRateThrottle keyed by client IP even for logged-in users (DRF's keys them by user id)."""

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class OriginalsBurstThrottle(SimpleRateThrottle):
    """Originals per client IP: a mass downloader (dozens of parallel fetches) hits this in seconds, a viewer never."""
    scope = 'original_burst'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class OriginalsThrottle(OriginalsBurstThrottle):
    """The same per hour: a slow crawler that stays under the burst limit."""
    scope = 'original'


class EmailScopedRateThrottle(ScopedRateThrottle):
    """Same scope and rate, keyed by the `email` in the body: limits mail to one address from many IPs."""

    def get_cache_key(self, request, view):
        email = request.data.get('email') if hasattr(request.data, 'get') else None
        if not isinstance(email, str) or not email.strip():
            return None  # the serializer rejects it anyway
        return self.cache_format % {'scope': self.scope, 'ident': 'email:' + email.strip().lower()}
