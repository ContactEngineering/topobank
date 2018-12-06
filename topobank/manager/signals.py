from django.db.models.signals import pre_delete
from django.dispatch import receiver
import os

from .models import Topography

@receiver(pre_delete, sender=Topography)
def remove_files(sender, instance, **kwargs):
    if instance.image:
        image_path = instance.image.path
        if os.path.exists(image_path):
            os.remove(image_path)

    # TODO remove data file, if no longer needed (there could be other topographies using it)
