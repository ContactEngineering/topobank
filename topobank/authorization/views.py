from django.http import HttpResponseBadRequest
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from ..organizations.models import resolve_organization
from ..users.models import resolve_user
from .models import Permissions, PermissionSet
from .serializers import (
    OrganizationPermissionSerializer,
    PermissionSetSerializer,
    UserPermissionSerializer,
)


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
    viewsets.GenericViewSet, mixins.RetrieveModelMixin
):
    queryset = PermissionSet.objects.all()
    serializer_class = PermissionSetSerializer
    permission_classes = [PermissionSetPermission]


@api_view(["POST"])
def add_user(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")
    user = resolve_user(request.data.get("user"))
    allow = request.data.get("allow")
    if allow not in {
        Permissions.view.name,
        Permissions.edit.name,
        Permissions.full.name,
    }:
        return HttpResponseBadRequest(
            f"`allow` must be one of '{Permissions.view.name}', '{Permissions.edit.name}', '{Permissions.full.name}'"
        )
    permission_set.grant_for_user(user, allow)
    serializer = UserPermissionSerializer(
        permission_set.user_permissions.get(user=user),
        context={'request': request}
    )
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def remove_user(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")
    user = resolve_user(request.data.get("user"))
    permission_set.revoke_from_user(user)
    return Response({}, status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def add_organization(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")
    organization = resolve_organization(request.data.get("organization"))
    allow = request.data.get("allow")
    if allow not in {
        Permissions.view.name,
        Permissions.edit.name,
        Permissions.full.name,
    }:
        return HttpResponseBadRequest(
            f"`allow` must be one of {Permissions.view.name}, {Permissions.edit.name}, {Permissions.full.name}"
        )
    permission_set.grant_for_organization(organization, allow)
    serializer = OrganizationPermissionSerializer(
        permission_set.organization_permissions.get(organization=organization),
        context={'request': request}
    )
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def remove_organization(request, pk: int):
    permission_set = PermissionSet.objects.get(pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")
    organization = resolve_organization(request.data.get("organization"))
    permission_set.revoke_from_organization(organization)
    return Response({}, status=status.HTTP_204_NO_CONTENT)
