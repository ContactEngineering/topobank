from urllib.parse import urlparse

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.utils import ProgrammingError
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from rest_framework.reverse import reverse

from .anonymous import get_anonymous_user


class ORCIDException(Exception):
    pass


class User(AbstractUser):
    # First name and last name (of the default `AbstractUser` model) do not cover name
    # patterns around the globe.
    name = models.CharField(_("Name of User"), max_length=255)

    # Load anonymous user once and cache to avoid further database hits
    anonymous_user = None

    def __str__(self):
        orcid_id = self.orcid_id
        if orcid_id:
            return "{} ({})".format(self.name, orcid_id)
        else:
            return self.name

    def save(self, *args, **kwargs):
        # ensure the full name field is set
        if not self.name:
            self.name = f"{self.first_name} {self.last_name}"
        super().save(*args, **kwargs)

    def _get_anonymous_user(self):
        if self.anonymous_user is None:
            self.anonymous_user = get_anonymous_user()
        return self.anonymous_user

    def get_absolute_url(self, request=None):
        """URL of API endpoint for this user"""
        return reverse("users:user-v1-detail", kwargs={"pk": self.pk}, request=request)

    def _orcid_info(self):  # TODO use local cache
        try:
            from allauth.socialaccount.models import SocialAccount
        except:  # noqa: E722
            raise ORCIDException("ORCID authentication not configured.")

        try:
            social_account = SocialAccount.objects.get(user_id=self.id)
        except SocialAccount.DoesNotExist as exc:
            raise ORCIDException("No ORCID account existing for this user.") from exc
        except SocialAccount.MultipleObjectsReturned as exc:
            raise ORCIDException(
                "Cannot retrieve ORCID: Multiple social accounts returned."
            ) from exc

        try:
            orcid_info = social_account.extra_data["orcid-identifier"]
        except Exception as exc:
            raise ORCIDException(
                "Cannot retrieve ORCID info from local database."
            ) from exc

        return orcid_info

    @property
    def orcid_id(self) -> str:
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
            return self._orcid_info()["path"]
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
            return self._orcid_info()["uri"]
        except ORCIDException:  # noqa: E722
            return None

    @property
    def is_anonymous(self):
        """
        Return whether user is anonymous.

        We have a piece of middleware, that replaces the default anonymous
        user with our own `AnonymousUser`. This is needed to give
        the world (as the anonymous user) access to published data sets.
        Since this anonymous user is a real user, `is_anonymous`
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

        We have a piece of middleware, that replaces the default anonymous
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


def resolve_user(url):
    """Resolve user from URL or ID"""
    try:
        id = int(url)
        return User.objects.get(pk=id)
    except ValueError:
        match = resolve(urlparse(url).path)
        if match.view_name != "users:user-v1-detail":
            raise ValueError("URL does not resolve to an User instance")
        return User.objects.get(**match.kwargs)
