from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.utils import ProgrammingError

from .anonymous import get_anonymous_user


class User(AbstractUser):
    orcid_id = models.CharField(max_length=19, default="0000-0000-0000-0000")
    name = models.CharField("Name of User", blank=True, max_length=255, default="")

    # Load anonymous user once and cache to avoid further database hits
    anonymous_user = None

    class Meta:
        app_label = 'users'

    def __str__(self):
        if self.orcid_id and self.orcid_id != "0000-0000-0000-0000":
            return f"{self.name} ({self.orcid_id})"
        return self.name

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"{self.first_name} {self.last_name}"
        super().save(*args, **kwargs)

    def _get_anonymous_user(self):
        if self.anonymous_user is None:
            self.anonymous_user = get_anonymous_user()
        return self.anonymous_user

    @property
    def is_anonymous(self):
        try:
            return self.id == self._get_anonymous_user().id
        except (ProgrammingError, self.DoesNotExist):
            return super().is_anonymous

    @property
    def is_authenticated(self):
        try:
            return self.id != self._get_anonymous_user().id
        except (ProgrammingError, self.DoesNotExist):
            return super().is_authenticated

    def orcid_uri(self):
        return f"https://orcid.org/{self.orcid_id}"

    @classmethod
    def resolve(cls, url):
        """Resolve user from URL or ID"""
        from urllib.parse import urlparse

        from django.urls import resolve
        try:
            pk = int(url)
            return cls.objects.get(pk=pk)
        except ValueError:
            match = resolve(urlparse(url).path)
            if match.view_name != "users:user-v1-detail":
                raise ValueError("URL does not resolve to a User instance")
            return cls.objects.get(**match.kwargs)
