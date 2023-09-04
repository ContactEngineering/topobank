import logging

from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_delete, post_delete, pre_save, post_save
from django.dispatch import receiver

from allauth.account.signals import user_logged_in
from notifications.models import Notification

from .models import Topography, Surface
from .views import DEFAULT_SELECT_TAB_STATE
from .utils import recursive_delete

_log = logging.getLogger(__name__)


# @receiver(post_save, sender=Surface)
# def grant_surface_permissions_to_owner(sender, instance, created, **kwargs):
#
#     if created:
#
#         # problem that perm does not exist
#
#         from django.contrib.auth.models import Permission
#
#         # 1. Check all permissions available
#         # surface_ct = ContentType.objects.get_for_model(Surface)
#         surface_ct = ContentType.objects.get(model="surface")
#         all_perms = [(p.codename, p.content_type, p.content_type == surface_ct, p.content_type.id, surface_ct.id) for p in Permission.objects.all() if 'surface' in p.codename]
#         import pprint
#         _log.info(f"All perms: {pprint.pformat(all_perms)}")
#
#         # 1.b Check all content_types
#         _log.info(f"Content Type:\n{pprint.pformat([(ct.app_label, ct.model, ct.id) for ct in ContentType.objects.all()])}")
#
#         # 2. check arguments
#         perm = Permission.objects.get(codename='view_surface', content_type=surface_ct)
#         _log.info(f"Perm: {perm}")
#
#         #
#         # Grant all permissions for this surface to its creator
#         #
#         for perm in ['view_surface', 'change_surface', 'delete_surface', 'share_surface', 'publish_surface']:
#             assign_perm(perm, instance.creator, instance)
#
#         # This should be only done when creating a surface,
#         # otherwise all permissions would be granted when editing a surface


@receiver(pre_delete, sender=Topography)
def remove_files(sender, instance, **kwargs):
    """Remove files associated with a topography instance before removal of the topography."""

    # ideally, we would reuse datafiles if possible, e.g. for
    # the example topographies. Currently I'm not sure how
    # to do it, because the file storage API always ensures to
    # have unique filenames for every new stored file.

    def delete_datafile(datafile_attr_name):
        """Delete datafile attached to the given attribute name."""
        try:
            datafile = getattr(instance, datafile_attr_name)
            _log.info(f'Deleting {datafile.name}...')
            datafile.delete()
        except Exception as exc:
            _log.warning(f"Topography id {instance.id}, attribute '{datafile_attr_name}': Cannot delete data file "
                         f"{datafile.name}', reason: {str(exc)}")

    datafile_path = instance.datafile.name
    squeezed_datafile_path = instance.squeezed_datafile.name
    thumbnail_path = instance.thumbnail.name

    delete_datafile('datafile')
    if instance.has_squeezed_datafile:
        delete_datafile('squeezed_datafile')
    if instance.has_thumbnail:
        delete_datafile('thumbnail')

    # Delete everything else after idiot check: Make sure files are actually stored under the storage prefix.
    # Otherwise we abort deletion.
    if datafile_path is not None and not datafile_path.startswith(instance.storage_prefix):
        _log.warning(f'Datafile is stored at location {datafile_path}, but storage prefix is '
                     f'{instance.storage_prefix}. I will not attempt to delete everything at this prefix.')
        return
    if squeezed_datafile_path is not None and not squeezed_datafile_path.startswith(instance.storage_prefix):
        _log.warning(f'Squeezed datafile is stored at location {squeezed_datafile_path}, but storage prefix is '
                     f'{instance.storage_prefix}. I will not attempt to delete everything at this prefix.')
        return
    if thumbnail_path is not None and not thumbnail_path.startswith(instance.storage_prefix):
        _log.warning(f'Thumbnail is stored at location {thumbnail_path}, but storage prefix is '
                     f'{instance.storage_prefix}. I will not attempt to delete everything at this prefix.')
        return
    recursive_delete(instance.storage_prefix)


@receiver(pre_save, sender=Topography)
def set_creator_if_needed(sender, instance, **kwargs):
    if instance.creator is None:
        instance.creator = instance.surface.creator


@receiver(post_save, sender=Topography)
def invalidate_cached_topography(sender, instance, **kwargs):
    """After a topography has been changed, we can't use the cached version any more."""
    cache.delete(instance.cache_key())


def _remove_notifications(instance):
    ct = ContentType.objects.get_for_model(instance)
    Notification.objects.filter(target_object_id=instance.id, target_content_type=ct).delete()


@receiver(post_delete, sender=Surface)
def remove_notifications_for_surface(sender, instance, using, **kwargs):
    _remove_notifications(instance)


@receiver(post_delete, sender=Topography)
def remove_notifications_for_topography(sender, instance, using, **kwargs):
    _remove_notifications(instance)


@receiver(user_logged_in)
def set_default_select_tab_state(request, user, **kwargs):
    """At each login, the state of the select tab should be reset.
    """
    request.session['select_tab_state'] = DEFAULT_SELECT_TAB_STATE
