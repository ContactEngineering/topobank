from rest_framework import viewsets, mixins
from rest_framework.permissions import BasePermission, SAFE_METHODS

from topobank.authorization.models import PermissionSet
from topobank.authorization.serializers import PermissionSetSerializer


class PermissionSetPermission(BasePermission):
    """
    Handle permissions for accessing permission sets.
    Users can only edit permission sets with "full" permission.
    """

    def has_permission(self, request, view):
        if not request.user or request.user.is_anonymous:
            return False

        return True

    def has_object_permission(self, request, view, obj: PermissionSet):
        if not request.user or request.user.is_anonymous:
            return False
        elif request.method in SAFE_METHODS:
            return obj.user_has_permission(request.user, "view")
        else:
            return obj.user_has_permission(request.user, "full")


class PermissionSetViewSet(
    viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.UpdateModelMixin
):
    queryset = PermissionSet.objects.all()
    serializer_class = PermissionSetSerializer
    permission_classes = [PermissionSetPermission]
