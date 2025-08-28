from rest_framework.permissions import SAFE_METHODS, BasePermission


class UserPermission(BasePermission):
    """
    Handle permissions for accessing users.
    * Staff users can do everything
    * Users can only see users in their own organizations
    * Users can only edit themselves
    """

    def has_permission(self, request, view):
        if not request.user or request.user.is_anonymous:
            return False

        if request.user.is_staff:
            return True
        else:
            return request.method in ("PATCH", "PUT", *SAFE_METHODS)

    def has_object_permission(self, request, view, obj):
        if not request.user or request.user.is_anonymous:
            return False
        # Admin users can do any operation on the users
        elif request.user.is_staff:
            return True
        # SAFE_METHODS are read operations
        elif request.method in SAFE_METHODS:
            # Read access is granted if the users are in the same groups
            return (
                len(
                    set(obj.groups.values_list("id", flat=True))
                    & set(request.user.groups.values_list("id", flat=True))
                )
                > 0
            )
        # This is a PATCH or PUT operation
        else:
            # Write access is only granted if the user is admin or if the user
            # tries to edit itself (e.g. changing name or email address)
            return obj == request.user
