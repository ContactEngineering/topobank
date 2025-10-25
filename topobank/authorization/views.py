from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from ..organizations.models import resolve_organization
from ..users.models import resolve_user
from .models import PermissionSet
from .serializers import (
    GrantOrganizationRequestSerializer,
    GrantUserRequestSerializer,
    OrganizationPermissionSerializer,
    PermissionSetSerializer,
    RevokeOrganizationRequestSerializer,
    RevokeUserRequestSerializer,
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


class PermissionSetViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = PermissionSet.objects.all()
    serializer_class = PermissionSetSerializer
    permission_classes = [PermissionSetPermission]


@extend_schema(
    request=GrantUserRequestSerializer,
    responses={201: UserPermissionSerializer},
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Grant user access to a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def grant_user(request, pk: int):
    permission_set = get_object_or_404(PermissionSet, pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = GrantUserRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = resolve_user(serializer.validated_data["user"])
    allow = serializer.validated_data["allow"]
    permission_set.grant_for_user(user, allow)

    response_serializer = UserPermissionSerializer(
        permission_set.user_permissions.get(user=user),
        context={'request': request}
    )
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=RevokeUserRequestSerializer,
    responses={204: None},
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Revoke user access from a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def revoke_user(request, pk: int):
    permission_set = get_object_or_404(PermissionSet, pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = RevokeUserRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = resolve_user(serializer.validated_data["user"])
    permission_set.revoke_from_user(user)
    return Response({}, status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    request=GrantOrganizationRequestSerializer,
    responses={201: OrganizationPermissionSerializer},
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Grant organization access to a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def grant_organization(request, pk: int):
    permission_set = get_object_or_404(PermissionSet, pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = GrantOrganizationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    organization = resolve_organization(serializer.validated_data["organization"])
    allow = serializer.validated_data["allow"]
    permission_set.grant_for_organization(organization, allow)

    response_serializer = OrganizationPermissionSerializer(
        permission_set.organization_permissions.get(organization=organization),
        context={'request': request}
    )
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=RevokeOrganizationRequestSerializer,
    responses={204: None},
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Revoke organization access from a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def revoke_organization(request, pk: int):
    permission_set = get_object_or_404(PermissionSet, pk=pk)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = RevokeOrganizationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    organization = resolve_organization(serializer.validated_data["organization"])
    permission_set.revoke_from_organization(organization)
    return Response({}, status=status.HTTP_204_NO_CONTENT)
