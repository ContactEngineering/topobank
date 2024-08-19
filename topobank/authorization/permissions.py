from rest_framework.permissions import BasePermission


class Permission(BasePermission):
    METHOD_TO_PERM = {
        "GET": "read",
        "OPTIONS": "read",
        "HEAD": "read",
        "POST": "edit",
        "PUT": "edit",
        "PATCH": "edit",
        "DELETE": "edit",
    }

    def has_object_permission(self, request, view, obj):
        obj.permissions.authorize_user(
            request.user, self.METHOD_TO_PERM[request.method]
        )
