from django.http import Http404
from rest_framework.permissions import SAFE_METHODS, DjangoObjectPermissions

from .models import Manifest


class ObjectPermissions(DjangoObjectPermissions):
    """
    Add restrictions to GET, OPTIONS and HEAD that are not present in the
    default `DjangoObjectPermissions`.
    """
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': ['%(app_label)s.view_%(model_name)s'],
        'HEAD': ['%(app_label)s.view_%(model_name)s'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

    def has_permission(self, request, view):
        # Permissions are handled on a per-object basis
        return True


class ParentObjectPermissions(ObjectPermissions):
    """
    Delegate permissions check to read/write/etc the parent `Surface` container
    object, not the actual `Topography` or `Tag`.

    Note that the model still needs to have correct permissions, i.e. a
    `Topography` needs to have permission `manager.add_topography` etc set.
    """
    parent_property = 'surface'

    def get_permission_responsible_object(self, obj):
        return getattr(obj, self.parent_property)

    def has_object_permission(self, request, view, obj):
        user = request.user

        parent_obj = self.get_permission_responsible_object(obj)

        required_perms = self.get_required_object_permissions(request.method, parent_obj.__class__)

        if not user.has_perms(required_perms, parent_obj):
            # If the user does not have permissions we need to determine if
            # they have read permissions to see 403, or not, and simply see
            # a 404 response.

            if request.method in SAFE_METHODS:
                # Read permissions already checked and failed, no need
                # to make another lookup.
                raise Http404

            read_perms = self.get_required_object_permissions('GET', parent_obj.__class__)
            if not user.has_perms(read_perms, parent_obj):
                raise Http404

            # Has read permissions.
            return False

        return True


class FileManifestObjectPermissions(ParentObjectPermissions):
    """
    Delegate permissions check to the parent object.
    This might be either a `Surface` or a `Topography` object.
    """

    def get_permission_responsible_object(self, obj: Manifest):
        parent_type, parent_obj = obj.parent.get_owner()
        if parent_type == "surface":
            return parent_obj
        elif parent_type == "topography":
            return parent_obj.surface
        else:
            raise ValueError("The parent type should be one of `surface` or `topography`")
