from django.shortcuts import reverse
from guardian.shortcuts import get_anonymous_user

# some abbreviations in order to save time on every request
ACCOUNT_SIGNUP_URL = reverse('account_signup')
ACCOUNT_LOGIN_URL = reverse('account_login')


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
        if not (request.user.is_authenticated
                or request.path == ACCOUNT_SIGNUP_URL or request.path == ACCOUNT_LOGIN_URL):
            request.user = get_anonymous_user()

        # mostly, we replace the anonymous user with guardian's AnonymousUser,
        # except when the URL for account signup is called. This is needed
        # for a test. Same for account login, this is needed for the browser
        # tests, because we don't wont to login with an orcid there.

        response = get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    return middleware

