from django.conf import settings
from django.contrib.auth import get_user_model

try:
    ANONYMOUS_USER_NAME = settings.ANONYMOUS_USER_NAME
except AttributeError:
    ANONYMOUS_USER_NAME = "AnonymousUser"


def get_anonymous_user():
    """
    Returns ``User`` instance (not ``AnonymousUser``) depending on
    ``ANONYMOUS_USER_NAME`` configuration.
    """
    User = get_user_model()
    lookup = {User.USERNAME_FIELD: ANONYMOUS_USER_NAME}
    return User.objects.get(**lookup)
