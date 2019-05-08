from django.db.models.signals import pre_delete, post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

import logging

from .models import Topography, Surface

_log = logging.getLogger(__name__)

@receiver(post_save, sender=Surface)
def grant_permissions_to_owner(sender, instance, created, **kwargs):

    if created:
        #
        # Grant all permissions for this surface to its owner
        #
        for perm in ['view_surface', 'change_surface', 'delete_surface', 'share_surface']:
            assign_perm(perm, instance.user, instance)

        # This should be only done when creating a surface,
        # otherwise all permissions would be granted when editing a surface


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

