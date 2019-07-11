from django.db.models.signals import pre_delete
from django.dispatch import receiver

from django.core.files.storage import default_storage
import os.path

import logging

from .models import Analysis

_log = logging.getLogger(__name__)

@receiver(pre_delete, sender=Analysis)
def remove_storage_files(sender, instance, **kwargs):

    prefix = instance.storage_prefix

    try:
        old_dirs, old_files = default_storage.listdir(prefix)
        for fn in old_files:
            fn = os.path.join(prefix, fn)
            _log.info("Deleting {}..".format(fn))
            default_storage.delete(fn)

        # in case the prefix also exists as "file", e.g. as directory
        # in a normal file system, also delete the prefix
        if default_storage.exists(prefix):
            _log.info("Deleting {}..".format(prefix))
            default_storage.delete(prefix)

    except FileNotFoundError:
        _log.info("No files found in {} for deletion".format(prefix))
    except Exception as exc:
        _log.error("Problem while deleting data for analysis {}, storage prefix {}. Reason: {}".format(
                   instance.id, prefix, str(exc)))
