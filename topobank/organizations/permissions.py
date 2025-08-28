from rest_framework.permissions import SAFE_METHODS, BasePermission


class OrganizationPermission(BasePermission):
    """
    Allows write access only to admin users. Users can only access organizations which
    they are members of.
    """

    def has_permission(self, request, view):
        if not request.user or request.user.is_anonymous:
            return False

        return bool(request.user.is_staff or request.method in SAFE_METHODS)

    def has_object_permission(self, request, view, obj):
        if not request.user or request.user.is_anonymous:
            return False
        # Admin users can do any operation on organizations
        elif request.user.is_staff:
            return True
        # Read access to normal users is granted if the users are members of
        # the organization they are accessing
        return obj.group.id in request.user.groups.values_list("id", flat=True)
