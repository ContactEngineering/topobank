from django.db.models.signals import pre_delete, post_delete, pre_save, post_save
from django.dispatch import receiver
from django.core.cache import cache
from guardian.shortcuts import assign_perm
from notifications.models import Notification
from django.contrib.contenttypes.models import ContentType
from allauth.account.signals import user_logged_in
import logging

from .models import Topography, Surface
from .views import DEFAULT_SELECT_TAB_STATE

_log = logging.getLogger(__name__)


@receiver(post_save, sender=Surface)
def grant_permissions_to_owner(sender, instance, created, **kwargs):

    if created:
        #
        # Grant all permissions for this surface to its creator
        #
        for perm in ['view_surface', 'change_surface', 'delete_surface', 'share_surface', 'publish_surface']:
            assign_perm(perm, instance.creator, instance)

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


@receiver(post_delete, sender=Topography)
def invalidate_surface_analyses(sender, instance, **kwargs):
    """All surface analyses have to be invalidated if a topography is deleted."""
    instance.surface.analyses.all().delete()


@receiver(pre_save, sender=Topography)
def set_creator_if_needed(sender, instance, **kwargs):
    if instance.creator is None:
        instance.creator = instance.surface.creator


@receiver(post_save, sender=Topography)
def invalidate_cached_topography(sender, instance, **kwargs):
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
