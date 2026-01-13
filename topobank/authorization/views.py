from collections import defaultdict

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from ..organizations.models import resolve_organization
from ..users.models import User, resolve_user
from .models import ACCESS_LEVELS, PermissionSet
from .serializers import (
    GrantOrganizationRequestSerializer,
    GrantUserRequestSerializer,
    OrganizationPermissionSerializer,
    PermissionSetSerializer,
    PluginSerializer,
    RevokeOrganizationRequestSerializer,
    RevokeUserRequestSerializer,
    SharedPermissionSetSerializer,
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
        parameters=[
            OpenApiParameter(
                name="sets",
                type=int,
                many=True,
                location=OpenApiParameter.QUERY,
                description="List of permission set IDs to find user intersection",
                required=True,
                style="form",
                explode=True,
            )
        ],
        responses={200: SharedPermissionSetSerializer},
        description=(
            "Find users that have access to ALL of the specified permission sets. "
            "Returns each user with their lowest permission level across those sets. "
            "For example, if a user has 'full' permission in set A and 'view' permission in set B, "
            "the returned permission will be 'view'. "
            "The 'is_unique' field indicates whether the permission level is the same across all sets."
        ),
        summary="Get user intersection across permission sets",
        tags=["authorization"],
    )
    @action(detail=False, methods=["GET"], url_path="shared", url_name="shared")
    def shared_permissions(self, request, *args, **kwargs):
        """
        Given a list of permission set IDs, return users that are in ALL sets
        along with their lowest permission level across those sets.
        """
        requested_ids = request.query_params.getlist("sets")

        if not requested_ids:
            raise NotFound("No permission set IDs provided.")

        # Convert string IDs to integers
        try:
            requested_ids = [int(id_) for id_ in requested_ids]
        except ValueError:
            raise NotFound("Invalid permission set ID format.")

        # Verify all permission sets exist and are accessible
        # Use prefetch_related to optimize queries
        user_sets = PermissionSet.objects.for_user(request.user).filter(
            id__in=requested_ids
        ).prefetch_related(
            'user_permissions__user',
            'organization_permissions__organization__group__user_set'
        ).distinct()

        if not user_sets.exists():
            raise NotFound("No accessible permission sets found.")
        if user_sets.count() < len(requested_ids):
            raise NotFound("One or more permission sets do not exist or are inaccessible.")

        # Build a mapping of user_id -> list of (permission_set_id, permission_level)
        user_permissions_map = defaultdict(list)

        # Collect all user permissions across all permission sets
        for perm_set in user_sets:
            # Get direct user permissions
            for user_perm in perm_set.user_permissions.all():
                user_permissions_map[user_perm.user.id].append({
                    'permission_set_id': perm_set.id,
                    'allow': user_perm.allow,
                    'access_level': ACCESS_LEVELS[user_perm.allow]
                })

            # Get organization permissions
            for org_perm in perm_set.organization_permissions.all():
                # Get all users in this organization
                for user in org_perm.organization.group.user_set.all():
                    user_permissions_map[user.id].append({
                        'permission_set_id': perm_set.id,
                        'allow': org_perm.allow,
                        'access_level': ACCESS_LEVELS[org_perm.allow]
                    })

        # Find users that appear in ALL permission sets
        user_ids_to_perm_info = {}
        for user_id, perms_list in user_permissions_map.items():
            # Group by permission_set_id and get the maximum permission for each set
            perm_set_to_max_level = {}
            for perm in perms_list:
                ps_id = perm['permission_set_id']
                if (ps_id not in perm_set_to_max_level
                        or perm['access_level'] > perm_set_to_max_level[ps_id]['access_level']):
                    perm_set_to_max_level[ps_id] = perm

            # Check if user appears in all requested sets
            if len(perm_set_to_max_level) == len(requested_ids):
                # Find the minimum permission level across all sets
                min_perm = min(perm_set_to_max_level.values(), key=lambda x: x['access_level'])

                # Check if all permission levels are the same (is_unique)
                all_perms = list(perm_set_to_max_level.values())
                is_unique = all(p['allow'] == all_perms[0]['allow'] for p in all_perms)

                user_ids_to_perm_info[user_id] = {
                    'allow': min_perm['allow'],
                    'is_unique': is_unique
                }

        # Bulk fetch all users in a single query
        users = {u.id: u for u in User.objects.filter(id__in=user_ids_to_perm_info.keys())}

        # Build result data
        user_permissions_data = []
        for user_id, perm_info in user_ids_to_perm_info.items():
            user_permissions_data.append({
                'user': users[user_id],
                'allow': perm_info['allow'],
                'is_current_user': request.user.id == user_id,
                'is_unique': perm_info['is_unique']
            })

        # Sort by name for consistent ordering
        user_permissions_data.sort(key=lambda x: x['user'].name)

        # Use the SharedPermissionSetSerializer for the response
        response_data = {
            'user_permissions': user_permissions_data,
            'organization_permissions': []  # Empty for now, as we only return users
        }

        serializer = SharedPermissionSetSerializer(
            response_data, context={'request': request}
        )
        return Response(serializer.data)


@extend_schema(
    responses={200: PluginSerializer(many=True)},
    description="List all plugins available to the current user.",
    tags=["authorization"],
)
@api_view(["GET"])
@transaction.non_atomic_requests
def plugins_available(request):
    from .utils import get_user_available_plugins

    plugin_apps = get_user_available_plugins(request.user)
    serializer = PluginSerializer(
        plugin_apps, many=True, context={'request': request}
    )
    return Response(serializer.data)


@extend_schema(
    request=GrantUserRequestSerializer,
    responses={201: UserPermissionSerializer},
    parameters=[
        OpenApiParameter(
            name="id",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Grant user access to a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def grant_user(request, id: int):
    permission_set = get_object_or_404(PermissionSet, pk=id)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = GrantUserRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = resolve_user(serializer.validated_data["user"])
    allow = serializer.validated_data["allow"]
    if allow == "no-access":
        permission_set.revoke_from_user(user)
        return Response({}, status=status.HTTP_204_NO_CONTENT)
    else:
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
            name="id",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Revoke user access from a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def revoke_user(request, id: int):
    permission_set = get_object_or_404(PermissionSet, pk=id)
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
            name="id",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Grant organization access to a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def grant_organization(request, id: int):
    permission_set = get_object_or_404(PermissionSet, pk=id)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = GrantOrganizationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    organization = resolve_organization(serializer.validated_data["organization"])
    allow = serializer.validated_data["allow"]
    if allow == "no-access":
        permission_set.revoke_from_organization(organization)
        return Response({}, status=status.HTTP_204_NO_CONTENT)
    else:
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
            name="id",
            type=int,
            location=OpenApiParameter.PATH,
            description="Permission set ID",
        )
    ],
    description="Revoke organization access from a permission set. Requires 'full' permission on the permission set.",
    tags=["authorization"],
)
@api_view(["POST"])
def revoke_organization(request, id: int):
    permission_set = get_object_or_404(PermissionSet, pk=id)
    # The user needs 'full' permission to modify permissions
    permission_set.authorize_user(request.user, "full")

    # Validate request data using serializer
    serializer = RevokeOrganizationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    organization = resolve_organization(serializer.validated_data["organization"])
    permission_set.revoke_from_organization(organization)
    return Response({}, status=status.HTTP_204_NO_CONTENT)
