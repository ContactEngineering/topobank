import logging

from django.http import HttpResponseBadRequest
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response

import topobank.manager.v1.views as v1

from ...authorization.models import PermissionSet
from ...authorization.permissions import Permission
from ...taskapp.utils import run_task
from ..zip_model import ZipContainer
from .serializers import (
    SurfaceV2Serializer,
    TopographyV2Serializer,
    ZipContainerV2Serializer,
)

_log = logging.getLogger(__name__)


class SurfaceViewSet(v1.SurfaceViewSet):
    serializer_class = SurfaceV2Serializer


class TopographyViewSet(v1.TopographyViewSet):
    serializer_class = TopographyV2Serializer


class ZipContainerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ZipContainer.objects.all()
    serializer_class = ZipContainerV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, Permission]


@api_view(["POST"])
def download_surface(request: Request, surface_ids: str):
    # `surface_ids` is a comma-separated list of surface IDs as a string,
    # e.g. "1,2,3", we need to parse it
    try:
        surface_ids = [int(surface_id) for surface_id in surface_ids.split(",")]
    except ValueError:
        return HttpResponseBadRequest("Invalid surface ID(s).")

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


@extend_schema(responses=ZipContainerV2Serializer)
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_zip_finish(request: Request, pk: int):
    # Get ZIP container
    zip_container = ZipContainer.objects.get(pk=pk)
    zip_container.authorize_user(request.user)

    # Dispatch task
    run_task(zip_container)
    zip_container.save()  # run_task sets the initial task state to 'pe', so we need to save

    return Response({})
