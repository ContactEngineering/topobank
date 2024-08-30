import logging

from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from ..authorization.permissions import Permission
from .models import Manifest
from .serializers import ManifestSerializer

_log = logging.getLogger(__name__)


class FileManifestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Manifest.objects.all()
    serializer_class = ManifestSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, Permission]


@api_view(["POST"])
def upload_local(request, manifest_id: int):
    # Get manifest instance and authorize
    manifest = get_object_or_404(Manifest, id=manifest_id)
    manifest.authorize_user(request.user, "edit")

    # Check if there already is a file
    if manifest.file:
        return HttpResponseBadRequest(
            f"A file already exists for manifest {manifest}. Cannot accept upload."
        )

    _log.debug(f"Receiving uploaded files for {manifest}...")
    nb_files = 0
    for key, file in request.FILES.items():
        nb_files += 1
        if nb_files > 1:
            return HttpResponseBadRequest("Upload can only accept single files.")
        manifest.finish_upload(file)

    return Response({}, status=204)
