from rest_framework.permissions import BasePermission


class Permission(BasePermission):
    METHOD_TO_PERM = {
        "GET": "view",
        "OPTIONS": "view",
        "HEAD": "view",
        "POST": "edit",
        "PUT": "edit",
        "PATCH": "edit",
        "DELETE": "full",
    }

    def has_object_permission(self, request, view, obj):
        return obj.permissions.user_has_permission(
            request.user, self.METHOD_TO_PERM[request.method]
        )
