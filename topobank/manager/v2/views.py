from django.http import HttpResponseBadRequest
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from ...authorization.models import PermissionSet
from ...authorization.permissions import Permission
from ...taskapp.utils import run_task
from ..models import ZipContainer
from .serializers import ZipContainerSerializer


class ZipContainerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ZipContainer.objects.all()
    serializer_class = ZipContainerSerializer
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
        permissions=PermissionSet.objects.create(user=request.user, allow="view"))

    # Dispatch task
    run_task(zip_container, surface_ids=surface_ids)

    # Return status
    return Response({"url": zip_container.get_absolute_url()})


@api_view(["GET"])
def download_tag(request, name):
    # Create a ZIP container object
    zip_container = ZipContainer.objects.create(
        permissions=PermissionSet.objects.create(user=request.user, allow="view"))

    # Dispatch task
    run_task(zip_container, tag_name=name)

    # Return status
    return Response({"url": zip_container.get_absolute_url()})
