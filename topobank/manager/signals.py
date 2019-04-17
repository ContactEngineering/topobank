from django.db.models.signals import pre_delete
from django.dispatch import receiver
import logging

from .models import Topography

_log = logging.getLogger(__name__)

@receiver(pre_delete, sender=Topography)
def remove_files(sender, instance, **kwargs):

    # ideally, we would reuse datafiles if possible, e.g. for
    # the example topographies. Currently I'm not sure how
    # to do it, because the file storage API always ensures to
    # have unique filenames for every new stored file.

    try:
        instance.datafile.delete()
    except Exception as exc:
        _log.warning("Cannot delete data file '%s', reason: %s", instance.datafile.name, str(exc))

