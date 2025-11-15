from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Organization


class OrganizationPermission(BasePermission):
    """
    Allows write access only to admin users. Users can only access organizations which
    they are members of.
    """

    def has_permission(self, request, view):
        if not request.user or request.user.is_anonymous:
            return False

        # Staff users have full access. List access to normal users is allowed.
        if request.user.is_staff or request.method in SAFE_METHODS:
            return True

        # Only staff can create/update/delete
        return False

    def has_object_permission(self, request, view, obj):
        if not request.user or request.user.is_anonymous:
            return False

        # Admin users can do any operation on organizations
        if request.user.is_staff:
            return True

        # Read access to normal users is granted if they are members of the organization
        if request.method in SAFE_METHODS:
            return obj in Organization.objects.for_user(request.user)

        # Only staff can modify organizations
        return False
