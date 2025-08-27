from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from ..organizations.models import resolve_organization
from ..users.models import resolve_user
from .models import PermissionSet
from .serializers import PermissionSetSerializer


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


@api_view(["POST"])
@permission_classes([PermissionSetPermission])
def add_user(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    user = resolve_user(request.query_params.get("user"))
    allow = request.query_params.get("allow")
    permission_set.grant_for_user(user, allow)
    return Response({})


@api_view(["POST"])
@permission_classes([PermissionSetPermission])
def remove_user(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    user = resolve_user(request.query_params.get("user"))
    permission_set.revoke_from_user(user)
    return Response({})


@api_view(["POST"])
@permission_classes([PermissionSetPermission])
def add_organization(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    organization = resolve_organization(request.query_params.get("organization"))
    allow = request.query_params.get("allow")
    permission_set.grant_for_organization(organization, allow)
    return Response({})


@api_view(["POST"])
@permission_classes([PermissionSetPermission])
def remove_organization(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    organization = resolve_organization(request.query_params.get("organization"))
    permission_set.revoke_from_organization(organization)
    return Response({})
