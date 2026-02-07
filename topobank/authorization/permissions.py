from django.db.models import QuerySet
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
    i.e., only objects for which `obj.authorize_user(user, perm)` succeeds. Default is "view" permission.
    Object level permissions in the view can then further restrict access depending on the action or method.

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

        Uses a two-step optimization:
        1. First, get accessible object IDs (UNION automatically deduplicates)
        2. Then, filter the original queryset by those IDs

        This avoids expensive operations on all model columns (50+)
        while preserving the queryset's select_related/prefetch_related optimizations.
        """
        # Allow view to override permission level
        if hasattr(view, "get_permission_level"):
            perm = view.get_permission_level()
        elif hasattr(view, "permission_level"):
            perm = view.permission_level
        else:
            perm = "view"

        # Step 1: Get accessible IDs (UNION queries auto-deduplicate)
        # Note: _filter_for_user uses UNION queries internally but returns a regular queryset.
        # To maintain performance optimizations we need to materialize IDs here. Then we filter
        # the original queryset in step 2 with those IDs.
        accessible_ids = queryset.model.objects.for_user(
            request.user, perm
        ).values_list('id', flat=True)

        # Step 2: Filter original queryset by accessible IDs
        # This preserves all select_related/prefetch_related from get_queryset()
        return queryset.filter(id__in=accessible_ids)
