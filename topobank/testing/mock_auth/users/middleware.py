from .anonymous import get_anonymous_user


def anonymous_user_middleware(get_response):
    def middleware(request):
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            request.user = get_anonymous_user()
        return get_response(request)
    return middleware
