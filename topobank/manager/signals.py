import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver
from notifications.models import Notification

from ..authorization import get_permission_model
from .models import Surface, Topography
from .zip_model import ZipContainer

_log = logging.getLogger(__name__)

# Fields that contribute to the full-text search document. Saves that only
# touch other fields (e.g. task state updates) do not trigger a re-index.
_SURFACE_SEARCH_FIELDS = {"name", "description", "created_by"}
_TOPOGRAPHY_SEARCH_FIELDS = {"name", "description", "created_by"}


def _remove_notifications(instance):
    ct = ContentType.objects.get_for_model(instance)
    Notification.objects.filter(
        target_object_id=instance.id, target_content_type=ct
    ).delete()


@receiver(pre_delete, sender=Topography)
def pre_delete_topography(sender, instance, using, **kwargs):
    _remove_notifications(instance)
    instance.remove_files()


@receiver(post_delete, sender=Surface)
def post_delete_surface(sender, instance, using, **kwargs):
    _remove_notifications(instance)
    # Delete permission set, which triggers deletion of all other associated data.
    # Needs to be in post_delete to avoid recursion.
    instance.permissions.delete()


#
# Full-text search index maintenance: keep `Surface.search_vector` up to date
# whenever searchable content changes. `update_search_vector` performs a plain
# queryset update, so these handlers do not recurse.
#


def _searchable_fields_changed(update_fields, searchable_fields):
    """True if a save may have modified fields in the search document."""
    return update_fields is None or bool(set(update_fields) & searchable_fields)


@receiver(post_save, sender=Surface)
def update_surface_search_vector(sender, instance, created, update_fields, **kwargs):
    if created or _searchable_fields_changed(update_fields, _SURFACE_SEARCH_FIELDS):
        instance.update_search_vector()


@receiver(post_save, sender=Topography)
def update_search_vector_on_topography_save(
    sender, instance, created, update_fields, **kwargs
):
    if created or _searchable_fields_changed(
        update_fields, _TOPOGRAPHY_SEARCH_FIELDS
    ):
        _update_parent_search_vector(instance)


@receiver(post_delete, sender=Topography)
def update_search_vector_on_topography_delete(sender, instance, using, **kwargs):
    _update_parent_search_vector(instance)


def _update_parent_search_vector(topography):
    try:
        surface = topography.surface
    except Surface.DoesNotExist:
        # Parent is being deleted along with its topographies
        return
    if surface is not None:
        surface.update_search_vector()


@receiver(m2m_changed, sender=Surface.tags.through)
def update_search_vector_on_surface_tags_change(
    sender, instance, action, reverse, **kwargs
):
    if action in ("post_add", "post_remove", "post_clear") and not reverse:
        instance.update_search_vector()


@receiver(m2m_changed, sender=Topography.tags.through)
def update_search_vector_on_topography_tags_change(
    sender, instance, action, reverse, **kwargs
):
    if action in ("post_add", "post_remove", "post_clear") and not reverse:
        _update_parent_search_vector(instance)


@receiver(post_delete, sender=ZipContainer)
def post_delete_zip_container(sender, instance, **kwargs):
    """
    Delete the archive of a ZIP container together with the container.

    The `manifest` foreign key is SET_NULL, so deleting the container does not
    by itself remove the archive. Deleting the permission set the container owns
    cascades to the manifest, whose own `pre_delete` handler removes the file
    from storage. Has to happen in `post_delete` to avoid recursing back into
    the container through its own (cascading) permissions field.
    """
    try:
        instance.permissions.delete()
    except get_permission_model().DoesNotExist:
        # Already gone, nothing to do
        pass
