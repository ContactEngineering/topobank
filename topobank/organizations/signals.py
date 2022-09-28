from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import Group
# from django.apps import apps

from .models import Organization, DEFAULT_GROUP_NAME

import logging
_log = logging.getLogger(__name__)


@receiver(post_delete, sender=Organization)
def remove_org_group(sender, instance, **kwargs):
    """On deletion of an organization, the corresponding group should also be deleted.

    Only exception: The group named "all" should not be deleted.
    """
    if instance.group.name != DEFAULT_GROUP_NAME:
        _log.info(f"Deleting group '{instance.group.name}' because of deletion of organization '{instance.name}'.")
        instance.group.delete()


#
# The following code is maybe needed to include HTML snippets
# based on the availability of plugins (based on an idea
# presented by Raphael Michel on DjangoCon 19)
#
# class OrganizationFilteredSignal(django.dispatch.Signal):
#     """Signal which is filtered by organization"""
#
#     @staticmethod
#     def _is_active(organization, receiver):
#         """Returns True, if this receiver is active for this organization.
#
#         "Active" means "available" here. Later, when Plugins
#         can also be switched off, it will mean "available and enabled".
#         """
#         # find django application this receiver belongs to
#         search_path = receiver.__module__
#         app = None
#         while True:
#             try:
#                 app = apps.get_app_config(search_path)
#             except LookupError:
#                 if ("." not in search_path) or app:
#                     break
#             search_path, _ = search_path.rsplit(".", 1)
#         return organization and app and app.name in organization.plugins_available.split(",")
#
#     def send(self, sender: Organization, **kwargs):
#         """Send out signal and collect results.
#         """
#         if not self.receivers:
#             return []
#
#         return [
#             (receiver, receiver(signal=self, sender=sender, **kwargs))
#             for receiver in self.receivers(sender) if self._is_active(sender, receiver)
#         ]
