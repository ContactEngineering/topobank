from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.core.files.storage import FileSystemStorage
import logging
import os

from .models import Topography

_log = logging.getLogger(__name__)

@receiver(pre_delete, sender=Topography)
def remove_files(sender, instance, **kwargs):
    # remove image
    # TODO remove all image code
    # if instance.image:
    #     image_path = instance.image.path
    #     if os.path.exists(image_path):
    #         os.remove(image_path)

    # ideally, we would reuse datafiles if possible, e.g. for
    # the example topographies. Currently I'm not sure how
    # to do it, because the file storage API always ensures to
    # have unique filenames for every new stored file.
    #
    # datafile_path = instance.datafile.path
    # other_datafile_paths = [ t.datafile.path for t in Topography.objects.filter(~Q(id=instance.id))]
    # if datafile_path not in other_datafile_paths and os.path.exists(datafile_path):

    try:
        instance.datafile.delete()
    except Exception as exc:
        _log.warning("Cannot delete data file '%s', reason: %s", instance.datafile.name, str(exc))

