import logging

from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, pre_save, post_save
from django.dispatch import receiver

from allauth.account.signals import user_logged_in
from notifications.models import Notification

from .models import Topography, Surface
from .views import DEFAULT_SELECT_TAB_STATE

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
