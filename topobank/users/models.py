import os

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import pre_save
from django.db.utils import ProgrammingError
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from guardian.core import ObjectPermissionChecker
from guardian.mixins import GuardianUserMixin
from guardian.shortcuts import get_anonymous_user, get_objects_for_user

DEFAULT_GROUP_NAME = 'all'


class ORCIDException(Exception):
    pass


class User(GuardianUserMixin, AbstractUser):
    # First Name and Last Name do not cover name patterns
    # around the globe.
    name = models.CharField(_("Name of User"), max_length=255)

    # Load anonymous user once and cache to avoid further database hits
    anonymous_user = None

    def __str__(self):
        orcid_id = self.orcid_id
        if orcid_id is None or orcid_id == '':
            return self.name
        else:
            return "{} ({})".format(self.name, orcid_id)

    def _get_anonymous_user(self):
        if self.anonymous_user is None:
            self.anonymous_user = get_anonymous_user()
        return self.anonymous_user

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})

    def get_media_path(self):
        """Return relative path of directory for files of this user."""
        return os.path.join('topographies', 'user_{}'.format(self.id))

    def has_obj_perms(self, perm, objs):
        """Return permission for list of objects"""
        checker = ObjectPermissionChecker(self)
        checker.prefetch_perms(objs)
        return [checker.has_perm(perm, obj) for obj in objs]

    def _orcid_info(self):  # TODO use local cache
        try:
            from allauth.socialaccount.models import SocialAccount
        except:  # noqa: E722
            raise ORCIDException("ORCID authentication not configured.")

        try:
            social_account = SocialAccount.objects.get(user_id=self.id)
        except SocialAccount.DoesNotExist as exc:
            raise ORCIDException("No ORCID account existing for this user.") from exc

        try:
            orcid_info = social_account.extra_data['orcid-identifier']
        except Exception as exc:
            raise ORCIDException("Cannot retrieve ORCID info from local database.") from exc

        return orcid_info

    @property
    def orcid_id(self):
        """
        Return ORCID iD, a unique 16-digit identifier for researchers.

        This method attempts to retrieve the ORCID iD from the user's linked
        social account information. If the ORCID iD cannot be retrieved (e.g.,
        due to the user not having an ORCID account linked), the method returns
        None.

        Returns
        -------
        str or None
            The ORCID iD as a string if available, otherwise None.
        """
        try:
            return self._orcid_info()['path']
        except ORCIDException:
            return None

    def orcid_uri(self):
        """
        Return the URI to the user's ORCID account, if available.

        This method is defined as a method rather than a property to allow for the
        possibility of returning different URIs based on given keywords in the future.
        Currently, it attempts to retrieve the ORCID URI from the user's linked social
        account information. If the ORCID URI cannot be retrieved, for example, if the
        user does not have an ORCID account linked or if there is an issue accessing
        the information, the method returns None.

        Returns
        -------
        str or None
            The ORCID URI as a string if available, otherwise None.
        """
        try:
            return self._orcid_info()['uri']
        except ORCIDException:  # noqa: E722
            return None

    def is_sharing_with(self, user):
        """Returns True if this user is sharing sth. with given user."""
        from topobank.manager.models import Surface

        objs = get_objects_for_user(user, 'view_surface', klass=Surface)
        for o in objs:
            if o.creator == self:  # this surface is shared by this user
                return True
        return False  # nothing shared

    @property
    def is_anonymous(self):
        """Return whether user is anonymous.

        We have a piece of middleware, that replaces the default anymous
        user with django-guardian `AnonymousUser`. This is needed to give
        the world (as the anonymous user) access to published data sets.
        Since django-guardians anonymous user is a real user, `is_anonymous`
        returns False and `is_authenticated` returns True by default. We
        adjust these properties here to reflect the anonymous state of the
        user.
        """
        try:
            # we might get an exception if the migrations
            # haven't been performed yet
            return self.id == self._get_anonymous_user().id
        except (ProgrammingError, self.DoesNotExist):
            return super().is_anonymous

    @property
    def is_authenticated(self):
        """Return whether user is anonymous.

        We have a piece of middleware, that replaces the default anymous
        user with django-guardian `AnonymousUser`. This is needed to give
        the world (as the anonymous user) access to published data sets.
        Since django-guardians anonymous user is a real user, `is_anonymous`
        returns False and `is_authenticated` returns True by default. We
        adjust these properties here to reflect the anonymous state of the
        user.
        """
        try:
            # we might get an exception if the migrations
            # haven't been performed yet
            return self.id != self._get_anonymous_user().id
        except (ProgrammingError, self.DoesNotExist):
            return super().is_anonymous

    class Meta:
        permissions = (
            ("can_skip_terms", "Can skip all checkings for terms and conditions."),
        )


#
# ensure the full name field is set
#
@receiver(pre_save, sender=User)
def ensure_name_field_set(sender, instance, **kwargs):
    if not instance.name:
        instance.name = f"{instance.first_name} {instance.last_name}"
