from rest_framework.throttling import ScopedRateThrottle


class IPScopedRateThrottle(ScopedRateThrottle):
    """ScopedRateThrottle keyed by client IP even for logged-in users (DRF's keys them by user id)."""

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class EmailScopedRateThrottle(ScopedRateThrottle):
    """Same scope and rate, keyed by the `email` in the body: limits mail to one address from many IPs."""

    def get_cache_key(self, request, view):
        email = request.data.get('email') if hasattr(request.data, 'get') else None
        if not isinstance(email, str) or not email.strip():
            return None  # the serializer rejects it anyway
        return self.cache_format % {'scope': self.scope, 'ident': 'email:' + email.strip().lower()}
