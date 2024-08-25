import logging

from django.conf import settings
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from ..authorization.permissions import Permission
from .models import Manifest
from .serializers import ManifestSerializer
from .upload import FileUploadService
from .utils import generate_storage_path

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
def upload_finished(request, manifest_id: int):
    # Get manifest instance and authorize
    manifest = get_object_or_404(Manifest, id=manifest_id)
    manifest.authorize_user(request.user, "edit")

    if settings.USE_S3_STORAGE:
        # Check if there already is a file
        if manifest.file:
            return HttpResponseBadRequest(
                f"A file already exists for manifest {manifest}. Cannot finalize upload."
            )

        # Set storage location to file that was just uploaded
        storage_path = generate_storage_path(manifest, manifest.file_name)
        manifest.file = manifest.file.field.attr_class(
            manifest, manifest.file.field, storage_path
        )

    FileUploadService(request.user).finish(manifest=manifest)
    return Response({}, status=204)


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
    for filename, file in request.FILES.items():
        nb_files += 1
        if nb_files > 1:
            return HttpResponseBadRequest("Upload can only accept single files.")
        FileUploadService(request.user).upload_local(manifest=manifest, file=file)

    return Response({}, status=204)
