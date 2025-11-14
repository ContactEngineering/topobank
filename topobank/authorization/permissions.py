from django.db.models import QuerySet
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.filters import BaseFilterBackend
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

VIEW = "view"
EDIT = "edit"
FULL = "full"

METHOD_TO_PERM = {
    "GET": VIEW,
    "OPTIONS": VIEW,
    "HEAD": VIEW,
    "POST": EDIT,
    "PUT": EDIT,
    "PATCH": EDIT,
    "DELETE": FULL,
}


class ObjectPermission(BasePermission):
    """
    Permission class to check object-level permissions based on user and method.

    Requires that the object has an `authorize_user` method that accepts
    a user and permission level.
    """
    def has_object_permission(self, request, view, obj):
        try:
            obj.authorize_user(request.user, METHOD_TO_PERM[request.method])
            return True
        except KeyError:
            # Unknown HTTP method
            return False


class PermissionFilterBackend(BaseFilterBackend):
    """
    Filter backend that restricts queryset to objects the user has permission to access.

    Requirements:
    - Model's manager must implement `for_user(user, permission)` method
      (e.g., using AuthorizedManager)
    - View MUST still use IsAuthenticated permission class

    Views can override the permission level by setting `permission_level` attribute:
        class MyView(viewsets.ModelViewSet):
            permission_level = "edit"  # All methods require edit permission

    Or by method:
        class MyView(viewsets.ModelViewSet):
            def get_permission_level(self):
                if self.action == 'special_action':
                    return "full"
                return METHOD_TO_PERM.get(self.request.method, "view")
    """

    def filter_queryset(
        self, request: Request, queryset: QuerySet, view: APIView
    ) -> QuerySet:
        """
        Filter queryset to only include objects the authenticated user can access.
        """
        # Allow view to override permission level
        if hasattr(view, "get_permission_level"):
            perm = view.get_permission_level()
        elif hasattr(view, "permission_level"):
            perm = view.permission_level
        else:
            try:
                perm = METHOD_TO_PERM.get(request.method)
            except KeyError:
                # Unknown HTTP method (CONNECT, TRACE, etc.)
                raise MethodNotAllowed(request.method)

        return queryset.for_user(request.user, perm)
