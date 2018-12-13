from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.conf import settings

import os

class User(AbstractUser):

    # First Name and Last Name do not cover name patterns
    # around the globe.
    name = models.CharField(_("Name of User"), max_length=255)

    def __str__(self):
        return self.username

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})

    def get_media_path(self):
        return os.path.join(settings.MEDIA_ROOT, 'topographies', 'user_{}'.format(self.id))

#
# ensure that after user creation, a media diretory exists
#
@receiver(post_save, sender=User)
def ensure_media_dir_exists(sender, instance, **kwargs):
    if kwargs['created']:
        try:
            os.makedirs(instance.get_media_path())
        except FileExistsError:
            pass

#
# ensure the full name field is set
#
@receiver(pre_save, sender=User)
def ensure_name_field_set(sender, instance, **kwargs):
    if instance.name is None:
        instance.name = f"{instance.first_name} {instance.last_name}"



