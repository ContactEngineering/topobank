import logging

from guardian.shortcuts import assign_perm, remove_perm, get_users_with_perms, get_anonymous_user

from ..manager.utils import api_to_guardian
from ..users.utils import get_default_group

_log = logging.getLogger(__name__)


class PublicationException(Exception):
    """A general exception related to publications."""
    pass


class PublicationsDisabledException(PublicationException):
    """Publications are not allowed due to settings."""
    pass


class AlreadyPublishedException(PublicationException):
    """A surface has already been published."""
    pass


class NewPublicationTooFastException(PublicationException):
    """A new publication has been issued to fast after the former one."""

    def __init__(self, latest_publication, wait_seconds):
        self._latest_pub = latest_publication
        self._wait_seconds = wait_seconds

    def __str__(self):
        s = f"Latest publication for this surface is from {self._latest_pub.datetime}. "
        s += f"Please wait {self._wait_seconds} more seconds before publishing again."
        return s


class UnknownCitationFormat(Exception):
    """Exception thrown when an unknown citation format should be handled."""

    def __init__(self, flavor):
        self._flavor = flavor

    def __str__(self):
        return f"Unknown citation format flavor '{self._flavor}'."


class DOICreationException(Exception):
    pass


def set_publication_permissions(surface):
    """Sets all permissions as needed for publication.

    - removes edit, share and delete permission from everyone
    - add read permission for everyone
    """
    # Superusers cannot publish
    if surface.creator.is_superuser:
        raise PublicationException("Superusers cannot publish!")

    # Remove edit, share and delete permission from everyone
    users = get_users_with_perms(surface)
    for u in users:
        for perm in api_to_guardian('full'):
            remove_perm(perm, u, surface)

    # Add read permission for everyone
    assign_perm('view_surface', get_default_group(), surface)

    # Add read permission for anonymous user
    assign_perm('view_surface', get_anonymous_user(), surface)

    from guardian.shortcuts import get_perms
    # TODO for unknown reasons, when not in Docker, the published surfaces are still changeable
    # Here "remove_perm" does not work. We do not allow this. See GH 704.
    if 'change_surface' in get_perms(surface.creator, surface):
        raise PublicationException("Withdrawing permissions for publication did not work!")

