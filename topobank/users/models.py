from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.conf import settings
from allauth.socialaccount.models import SocialAccount
from guardian.mixins import GuardianUserMixin

import os



class ORCIDInfoMissingException(Exception):
    pass

class User(GuardianUserMixin, AbstractUser):

    # First Name and Last Name do not cover name patterns
    # around the globe.
    name = models.CharField(_("Name of User"), max_length=255)

    def __str__(self):
        return self.username

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})

    def get_media_path(self):
        """Return relative path of directory for files of this user."""
        return os.path.join('topographies', 'user_{}'.format(self.id))

    def _orcid_info(self):
        social_account = SocialAccount.objects.get(user_id=self.id)

        try:
            orcid_info = social_account.extra_data['orcid-identifier']
        except Exception as exc:
            raise ORCIDInfoMissingException("Cannot retrieve ORCID info from local database.") from exc

        return orcid_info

    @property
    def orcid_id(self):
        """Return ORCID iD, the 16-digit identifier as string in format XXXX-XXXX-XXXX-XXXX.

        :return: str
        :raises: ORCIDInfoMissingException
        """
        return self._orcid_info()['path']

    # defined as method, not property because we maybe later return other URI when a keyword is given
    def orcid_uri(self):
        """Return uri to ORCID account.

        :return: str
        :raises: ORCIDInfoMissingException
        """
        return self._orcid_info()['uri']

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



