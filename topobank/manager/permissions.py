from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from guardian.utils import get_user_obj_perms_model
from rest_framework.filters import BaseFilterBackend
from rest_framework.permissions import SAFE_METHODS, DjangoObjectPermissions

from .models import FileManifest, Surface


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

    def get_permission_responsible_object(self, obj: FileManifest):
        parent_type, parent_obj = obj.parent.get_owner()
        match parent_type:
            case "surface":
                return parent_obj
            case "topography":
                return parent_obj.surface
            case _:
                raise ValueError("The parent type should be one of `surface` or `topography`")


# From django-rest-framework-guardian:
# https://github.com/rpkilby/django-rest-framework-guardian/blob/master/src/rest_framework_guardian/filters.py
# Licensed under 3-clause BSD:
# https://github.com/rpkilby/django-rest-framework-guardian/blob/master/LICENSE
class ObjectPermissionsFilter(BaseFilterBackend):
    """
    A filter backend that limits results to those where the requesting user
    has read object level permissions.
    """
    perm_format = '%(app_label)s.view_%(model_name)s'
    shortcut_kwargs = {
        'accept_global_perms': False,
    }

    def filter_queryset(self, request, queryset, view):
        # We want to defer this import until runtime, rather than import-time.
        # See https://github.com/encode/django-rest-framework/issues/4608
        # (Also see #1624 for why we need to make this import explicitly)
        from guardian.shortcuts import get_objects_for_user

        user = request.user
        permission = self.perm_format % {
            'app_label': queryset.model._meta.app_label,
            'model_name': queryset.model._meta.model_name,
        }

        return get_objects_for_user(
            user, permission, queryset,
            **self.shortcut_kwargs)


# Adopted from django-rest-framework-guardian:
# https://github.com/rpkilby/django-rest-framework-guardian/blob/master/src/rest_framework_guardian/filters.py
# Licensed under 3-clause BSD:
# https://github.com/rpkilby/django-rest-framework-guardian/blob/master/LICENSE
class ParentObjectPermissionsFilter(BaseFilterBackend):
    """
    A filter backend that limits results to those where the requesting user
    has read object level permissions to a parent object.
    """
    perm_format = '%(app_label)s.view_%(model_name)s'
    shortcut_kwargs = {
        'accept_global_perms': False,
    }
    parent_property = 'surface'
    parent_model = Surface

    def filter_queryset(self, request, queryset, view):
        user = request.user

        # User model stores the per-object permissions
        ctype = ContentType.objects.get_for_model(self.parent_model)
        user_model = get_user_obj_perms_model(queryset.model)
        user_obj_perms_queryset = user_model.objects.filter(user=user).filter(permission__content_type=ctype)

        # Construct filter arguments that search for pk of parent model
        filter_kwargs = {f'{self.parent_property}__pk__in': user_obj_perms_queryset}
        return queryset.filter(**filter_kwargs)
