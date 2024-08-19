from rest_framework.permissions import BasePermission


class TagPermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        obj.authorize_user(request.user)
        # Permissions are granted if authenticated tag returns 1 or more
        # surfaces
        return len(obj.get_descendant_surfaces()) > 0
