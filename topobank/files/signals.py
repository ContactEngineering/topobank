from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Manifest


@receiver(pre_delete, sender=Manifest)
def pre_delete_manifest(sender, instance, **kwargs):
    # File must be deleted in signal, as the delete method is not triggered in a CASCADE
    # delete
    instance.file.delete(save=False)
