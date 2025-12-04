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
        return Surface.objects.for_user(self.request.user).filter(
            deletion_time__isnull=True
        ).select_related(
            'permissions',
            'created_by',
            'updated_by',
            'owned_by',
        ).prefetch_related(
            'topography_set',
        ).distinct().order_by('name')

    def perform_destroy(self, instance):
        """Perform soft delete by setting deletion_time instead of hard delete."""
        self._notify(instance, verb="delete")
        instance.lazy_delete()


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
        return Topography.objects.for_user(self.request.user).filter(
            Q(deletion_time__isnull=True) & Q(surface__deletion_time__isnull=True)
        ).select_related(
            'surface',
            'permissions',
            'created_by',
            'updated_by',
            'owned_by',
            'attachments',
            'thumbnail',
            'deepzoom',
        ).distinct().order_by('name')

    def get_serializer_class(self):
        if self.action == 'create':
            return TopographyV2CreateSerializer
        return super().get_serializer_class()

    def perform_destroy(self, instance):
        """Perform soft delete by setting deletion_time instead of hard delete."""
        instance.lazy_delete()


class ZipContainerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ZipContainer.objects.all()
    serializer_class = ZipContainerV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermission]


@extend_schema(request=None,
               responses=ZipContainerV2Serializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def download_surface(request: Request, surface_ids: str):
    # `surface_ids` is a comma-separated list of surface IDs as a string,
    # e.g. "1,2,3", we need to parse it
    try:
        surface_ids = [int(surface_id) for surface_id in surface_ids.split(",")]
    except ValueError:
        return HttpResponseBadRequest("Invalid surface ID(s).")

    # We need to check that the user has access to the requested surfaces
    surface_qs = Surface.objects.for_user(request.user).filter(
        id__in=surface_ids,
        deletion_time__isnull=True
    )
    if surface_qs.count() != len(surface_ids):
        invalid_ids = set(surface_ids) - set(surface_qs.values_list('id', flat=True))
        return HttpResponseBadRequest(f"One or more surfaces do not exist or are inaccessible: {invalid_ids}")
    # Create a ZIP container object
    zip_container = ZipContainer.objects.create(
        permissions=PermissionSet.objects.create(user=request.user, allow="view")
    )

    # Dispatch task
    run_task(zip_container, surface_ids=surface_ids)

    # Return status
    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )


@extend_schema(request=None,
               responses=ZipContainerV2Serializer)
@api_view(["POST"])
def download_tag(request: Request, name: str):
    # Create a ZIP container object
    zip_container = ZipContainer.objects.create(
        permissions=PermissionSet.objects.create(user=request.user, allow="view")
    )

    # Dispatch task
    run_task(zip_container, tag_name=name)

    # Return status
    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )


@extend_schema(request=None,
               responses=ZipContainerV2Serializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_zip_start(request: Request):
    # Create a ZIP container object
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
def upload_zip_finish(request: Request, pk: int):
    # Get ZIP container
    zip_container = get_object_or_404(ZipContainer, pk=pk)
    zip_container.authorize_user(request.user)

    # Dispatch task
    run_task(zip_container)
    zip_container.save()  # run_task sets the initial task state to 'pe', so we need to save

    return Response(
        ZipContainerV2Serializer(zip_container, context={"request": request}).data
    )
