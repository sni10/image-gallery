from django.utils.cache import patch_vary_headers


def vary_on_authorization(get_response):
    """API answers depend on the Bearer token (locked photos, signed links): shared caches must not mix them."""
    def middleware(request):
        response = get_response(request)
        patch_vary_headers(response, ['Authorization'])
        return response

    return middleware
