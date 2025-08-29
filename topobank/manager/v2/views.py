from django.http import HttpResponseBadRequest
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

import topobank.manager.v1.views as v1

from ...authorization.models import PermissionSet
from ...authorization.permissions import Permission
from ...taskapp.utils import run_task
from ..models import ZipContainer
from .serializers import (
    SurfaceV2Serializer,
    TopographyV2Serializer,
    ZipContainerV2Serializer,
)


class SurfaceViewSet(v1.SurfaceViewSet):
    serializer_class = SurfaceV2Serializer


class TopographyViewSet(v1.TopographyViewSet):
    serializer_class = TopographyV2Serializer


class ZipContainerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ZipContainer.objects.all()
    serializer_class = ZipContainerV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, Permission]


@api_view(["GET"])
def download_surface(request, surface_ids):
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


@api_view(["GET"])
def download_tag(request, name):
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
