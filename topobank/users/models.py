from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.db.utils import ProgrammingError

from guardian.core import ObjectPermissionChecker
from guardian.mixins import GuardianUserMixin
from guardian.shortcuts import get_objects_for_user, get_anonymous_user

import os

DEFAULT_GROUP_NAME = 'all'

class ORCIDException(Exception):
    pass


class User(GuardianUserMixin, AbstractUser):

    # First Name and Last Name do not cover name patterns
    # around the globe.
    name = models.CharField(_("Name of User"), max_length=255)

    def __str__(self):
        try:
            orcid_id = self.orcid_id
        except ORCIDException:
            orcid_id = None

        return "{} ({})".format(self.name, orcid_id if orcid_id else "no ORCID ID")

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
        except:
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
        """Return ORCID iD, the 16-digit identifier as string in format XXXX-XXXX-XXXX-XXXX.

        :return: str
        :raises: ORCIDInfoMissingException
        """
        return self._orcid_info()['path']

    # defined as method and not as property, because we maybe later return other URI when a keyword is given
    def orcid_uri(self):
        """Return uri to ORCID account or None if not available.

        :return: str or None
        """
        try:
            return self._orcid_info()['uri']
        except:
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
            return self.id == get_anonymous_user().id
        except ProgrammingError:
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
            return self.id != get_anonymous_user().id
        except ProgrammingError:
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
