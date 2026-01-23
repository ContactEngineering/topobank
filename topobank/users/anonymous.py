from functools import lru_cache

from django.conf import settings
from django.contrib.auth import get_user_model

try:
    ANONYMOUS_USER_NAME = settings.ANONYMOUS_USER_NAME
except AttributeError:
    ANONYMOUS_USER_NAME = "AnonymousUser"


@lru_cache(maxsize=1)
def get_anonymous_user():
    """
    Returns ``User`` instance (not ``AnonymousUser``) depending on
    ``ANONYMOUS_USER_NAME`` configuration.

    Cached with lru_cache to avoid repeated database queries during
    permission checks in list endpoints (e.g., 25 topographies per page
    would otherwise trigger 25 identical queries).
    """
    User = get_user_model()
    lookup = {User.USERNAME_FIELD: ANONYMOUS_USER_NAME}
    return User.objects.get(**lookup)
