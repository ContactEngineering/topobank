from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import backends
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from notifications.signals import notify
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response

from topobank.manager.v2.filters import SurfaceViewFilterSet, TopographyViewFilterSet
from topobank.supplib.mixins import UserUpdateMixin
from topobank.supplib.pagination import TopobankPaginator

from ...authorization.models import PermissionSet
from ...authorization.permissions import ObjectPermission, PermissionFilterBackend
from ...taskapp.utils import run_task
from ..models import Surface, Topography
from ..zip_model import ZipContainer
from .serializers import (
    SurfaceV2Serializer,
    TopographyV2CreateSerializer,
    TopographyV2Serializer,
    ZipContainerV2Serializer,
)


class SurfaceViewSet(UserUpdateMixin, viewsets.ModelViewSet):
    serializer_class = SurfaceV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermission]
    pagination_class = TopobankPaginator
    filter_backends = [PermissionFilterBackend, backends.DjangoFilterBackend]
    filterset_class = SurfaceViewFilterSet

    def _notify(self, instance, verb):
        user = self.request.user
        other_users = instance.permissions.user_permissions.filter(~Q(user__id=user.id))
        for u in other_users:
            notify.send(
                sender=user,
                verb=verb,
                recipient=u.user,
                description=f"User '{user.name}' {verb}d digital surface twin '{instance.name}'.",
            )

    def get_queryset(self):
        # PermissionFilterBackend handles permission filtering with two-step optimization
        # We just apply business logic filters and optimizations here
        return Surface.objects.select_related(
            'permissions',
            'created_by',
            'updated_by',
            'owned_by',
            'attachments',
        ).prefetch_related(
            'topography_set',
            'properties',
            'tags',
            'permissions__user_permissions',
            'permissions__user_permissions__user',
            'permissions__organization_permissions',
            'permissions__organization_permissions__organization',
        ).order_by('name')

    def list(self, request, *args, **kwargs):
        """Override list to initialize permission cache for performance"""
        # Initialize cache on user object to avoid repeated queries during serialization
        if request.user.is_authenticated:
            # Cache user groups once per request
            if not hasattr(request.user, '_cached_group_ids'):
                request.user._cached_group_ids = list(
                    request.user.groups.values_list('id', flat=True)
                )
        return super().list(request, *args, **kwargs)

    @transaction.atomic
    def perform_destroy(self, instance):
        """Perform soft delete by setting deletion_time instead of hard delete."""
        self._notify(instance, verb="delete")
        instance.lazy_delete()

    @transaction.atomic
    def perform_update(self, serializer):
        return super().perform_update(serializer)

    @transaction.atomic
    def perform_create(self, serializer):
        return super().perform_create(serializer)


@extend_schema_view(
    retrieve=extend_schema(
        description="Retrieve a specific Topography by its ID.",
    ),
    list=extend_schema(
        description="List all topographies accessible to the authenticated user. "
                    "Optionally filter by surface ID or tags.",
        parameters=[
            OpenApiParameter(
                name="link_file",
                type=bool,
                description="If set to true, the response will include the direct URL to the file (thumbnail).",
                required=False,
            ),
        ],
        request=None,
        responses={200: TopographyV2Serializer},
    )
)
class TopographyViewSet(UserUpdateMixin, viewsets.ModelViewSet):
    serializer_class = TopographyV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermission]
    pagination_class = TopobankPaginator
    filter_backends = [PermissionFilterBackend, backends.DjangoFilterBackend]
    filterset_class = TopographyViewFilterSet

    def get_queryset(self):
        # PermissionFilterBackend handles permission filtering with two-step optimization
        # We just apply business logic filters and optimizations here
        return Topography.objects.select_related(
            'surface',
            'permissions',
            'created_by',
            'updated_by',
            'owned_by',
            'attachments',
            'thumbnail',
            'datafile',
            'deepzoom',
            'squeezed_datafile',
        ).prefetch_related(
            'tags',
            'permissions__user_permissions',
            'permissions__user_permissions__user',
            'permissions__organization_permissions',
            'permissions__organization_permissions__organization',
        ).order_by('name')

    def get_serializer_class(self):
        if self.action == 'create':
            return TopographyV2CreateSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        """Override list to initialize permission cache for performance"""
        # Initialize cache on user object to avoid repeated queries during serialization
        if request.user.is_authenticated:
            # Cache user groups once per request
            if not hasattr(request.user, '_cached_group_ids'):
                request.user._cached_group_ids = list(
                    request.user.groups.values_list('id', flat=True)
                )

        # Get the filtered queryset and paginate it
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        # Build permission cache for the objects we'll serialize to avoid repeated get_for_user() calls
        # This is the critical optimization: compute permissions once per unique PermissionSet
        permission_cache = {}
        if request.user.is_authenticated:
            # Use the page if available, otherwise the full queryset
            objects_to_cache = page if page is not None else queryset
            for obj in objects_to_cache:
                # Only compute if we haven't seen this PermissionSet before
                if obj.permissions_id not in permission_cache:
                    permission_cache[obj.permissions_id] = obj.permissions.get_for_user(request.user)

        # Serialize with the permission cache in context
        context = {'permission_cache': permission_cache, 'request': request}
        if page is not None:
            serializer = self.get_serializer(page, many=True, context=context)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context=context)
        return Response(serializer.data)

    @transaction.atomic
    def perform_destroy(self, instance):
        """Perform soft delete by setting deletion_time instead of hard delete."""
        instance.lazy_delete()

    @transaction.atomic
    def perform_update(self, serializer):
        return super().perform_update(serializer)

    @transaction.atomic
    def perform_create(self, serializer):
        return super().perform_create(serializer)


class ZipContainerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ZipContainer.objects.all()
    serializer_class = ZipContainerV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermission]


@extend_schema(
    request=None,
    parameters=[
        OpenApiParameter(
            name="tag",
            type=str,
            description="Optional root tag to use as the starting point for the tree. "
                        "Only this tag and its descendants will be included. "
                        "Example: 'material' or 'material/steel'",
            required=False,
        ),
    ],
    responses={200: {
        "type": "object",
        "description": "A nested tree structure of all tags accessible to the user",
        "example": {
            "material": {
                "surface_count": 3,
                "children": {
                    "material/steel": {
                        "surface_count": 0,
                        "children": {
                            "material/steel/stainless": {
                                "surface_count": 5,
                                "children": {}
                            },
                            "material/steel/carbon": {
                                "surface_count": 5,
                                "children": {}
                            }
                        }
                    },
                    "material/aluminum": {
                        "surface_count": 7,
                        "children": {}
                    }
                }
            }
        }
    }},
    description="Returns the complete hierarchical tag tree for all tags accessible to the user. "
                "Each node includes 'surface_count' (number of surfaces with this exact tag, not descendants) "
                "and 'children' (nested child tags). Optionally filter by a root tag using ?tag=tag_name"
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def tag_tree(request: Request):
    """
    Returns the full hierarchical tag tree structure with surface counts.

    The response is a nested dictionary representing the complete tag hierarchy
    where each node contains 'surface_count' (surfaces with this exact tag) and
    'children' (nested child tags).

    Query parameters:
    - tag (optional): Root tag name to filter the tree. Only this tag and its
                      descendants will be included.

    Example response:
    {
        "material": {
            "surface_count": 3,
            "children": {
                "material/steel": {
                    "surface_count": 0,
                    "children": {
                        "material/steel/stainless": {
                            "surface_count": 5,
                            "children": {}
                        }
                    }
                }
            }
        }
    }
    """

    root_tag = request.query_params.get("tag")

    # Build query for surface-tag pairs with optional root filter
    # We only consider surfaces accessible to the user and not deleted
    query = (
        Surface.objects.for_user(request.user)
        .filter(tags__name__isnull=False)
        .values_list("id", "tags__name")
    )

    if root_tag:
        query = query.filter(
            Q(tags__name=root_tag) | Q(tags__name__startswith=f"{root_tag}/")
        )

    surface_tags = query.distinct()

    # Count unique surfaces per tag using defaultdict
    tag_to_surfaces = defaultdict(set)
    for surface_id, tag_name in surface_tags:
        tag_to_surfaces[tag_name].add(surface_id)

    # Convert to counts
    tag_counts = {tag: len(surfaces) for tag, surfaces in tag_to_surfaces.items()}

    if not tag_counts:
        return Response({})

    # Build tree structure
    if root_tag:
        # When root_tag is specified, build only the subtree
        # by stripping the root prefix from all paths
        root_prefix_len = len(root_tag)

        # Start with the root node
        tree = {
            root_tag: {
                "surface_count": tag_counts.get(root_tag, 0),
                "children": {}
            }
        }

        # Build only descendants
        for tag_name in sorted(tag_counts.keys()):
            if tag_name == root_tag:
                continue

            # For descendants, navigate relative to root
            if tag_name.startswith(f"{root_tag}/"):
                # Get the relative path after the root
                relative_path = tag_name[root_prefix_len + 1:]  # +1 for the "/"
                parts = relative_path.split("/")

                # Start from the root's children
                current = tree[root_tag]["children"]

                # Build path progressively from root
                for i, part in enumerate(parts):
                    full_path = f"{root_tag}/{'/'.join(relative_path.split('/')[:i + 1])}"

                    if full_path not in current:
                        current[full_path] = {
                            "surface_count": tag_counts.get(full_path, 0),
                            "children": {}
                        }
                    current = current[full_path]["children"]
    else:
        # Build full tree when no root specified
        tree = {}
        for tag_name in sorted(tag_counts.keys()):
            parts = tag_name.split("/")
            current = tree

            # Build path progressively
            for i, part in enumerate(parts):
                full_path = "/".join(parts[:i + 1])

                if full_path not in current:
                    current[full_path] = {
                        "surface_count": tag_counts.get(full_path, 0),
                        "children": {}
                    }
                current = current[full_path]["children"]

    return Response(tree)


@extend_schema(request=None,
               responses=ZipContainerV2Serializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def download_surface(request: Request, surface_ids: str):
    # `surface_ids` is a comma-separated list of surface IDs as a string,
    # e.g. "1,2,3", we need to parse it
    try:
        surface_ids = [int(surface_id) for surface_id in surface_ids.split(",")]
    except ValueError:
        return HttpResponseBadRequest("Invalid surface ID(s).")

    # We need to check that the user has access to the requested surfaces
    surface_qs = Surface.objects.for_user(request.user).filter(
        id__in=surface_ids
    )
    if surface_qs.count() != len(surface_ids):
        invalid_ids = set(surface_ids) - set(surface_qs.values_list('id', flat=True))
        return HttpResponseBadRequest(f"One or more surfaces do not exist or are inaccessible: {invalid_ids}")

    # Create ZIP container and dispatch task within transaction
    with transaction.atomic():
        zip_container = ZipContainer.objects.create(
            permissions=PermissionSet.objects.create(user=request.user, allow="view")
        )
        run_task(zip_container, surface_ids=surface_ids)
        zip_container.save()

    # Return status
    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )


@extend_schema(request=None,
               responses=ZipContainerV2Serializer)
@api_view(["POST"])
@transaction.non_atomic_requests
def download_tag(request: Request, name: str):
    # Create ZIP container and dispatch task within transaction
    with transaction.atomic():
        zip_container = ZipContainer.objects.create(
            permissions=PermissionSet.objects.create(user=request.user, allow="view")
        )
        run_task(zip_container, tag_name=name)
        zip_container.save()

    # Return status
    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )


@extend_schema(request=None,
               responses=ZipContainerV2Serializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def upload_zip_start(request: Request):
    # Create a ZIP container object within transaction
    with transaction.atomic():
        zip_container = ZipContainer.objects.create(
            permissions=PermissionSet.objects.create(user=request.user, allow="full")
        )

        # Create an empty manifest
        zip_container.create_empty_manifest()

    # Return status
    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )


@extend_schema(
    request=None,
    responses=ZipContainerV2Serializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def upload_zip_finish(request: Request, pk: int):
    # Get ZIP container
    zip_container = get_object_or_404(ZipContainer, pk=pk)
    zip_container.authorize_user(request.user)

    # Dispatch task after transaction commits
    with transaction.atomic():
        run_task(zip_container)
        zip_container.save()

    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )
