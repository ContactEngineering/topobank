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
        # The user object can only be accessed if the user is an admin or the user
        # is in the same group as the requesting user.
        return bool(
            request.user.is_staff
            or (
                request.method in SAFE_METHODS
                and len(
                    set(obj.groups.value_list("id"))
                    & set(request.user.groups.value_list("id"))
                )
                > 0
            )
        )
