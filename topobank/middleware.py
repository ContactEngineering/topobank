from django.conf import settings
from django.shortcuts import reverse
from django.urls import NoReverseMatch

from topobank.users.anonymous import get_anonymous_user

HEADLESS_ONLY = hasattr(settings, "HEADLESS_ONLY") and settings.HEADLESS_ONLY

# Default to headful mode, but allow to switch to headless mode
_no_anonymous_substitution_urls = []
if not HEADLESS_ONLY:
    # some abbreviations in order to save time on every request
    try:
        _no_anonymous_substitution_urls += [reverse("account_signup")]
    except NoReverseMatch:
        pass
    try:
        _no_anonymous_substitution_urls += [reverse("account_login")]
    except NoReverseMatch:
        pass


def anonymous_user_middleware(get_response):
    """Modify user of each request if not authenticated.

    Parameters
    ----------
    get_response
        Function which returns response giving a request.

    Returns
    -------
    Middleware function. Can be used in configuration
    of MIDDLEWARE.

    """

    def middleware(request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        if HEADLESS_ONLY:
            if not request.user.is_authenticated:
                request.user = get_anonymous_user()
        else:
            if not (
                request.user.is_authenticated
                or request.path in _no_anonymous_substitution_urls
            ):
                request.user = get_anonymous_user()

        # mostly, we replace the anonymous user with our own anonymous user,
        # except when the URL for account signup is called. This is needed
        # for a test. Same for account login, this is needed for the browser
        # supplib, because we don't wont to login with an orcid there.

        response = get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    return middleware
