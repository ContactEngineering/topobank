import logging

from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from topobank.authorization.permissions import EDIT, VIEW

from .models import Folder, Manifest
from .permissions import ManifestPermission
from .serializers import ManifestSerializer

_log = logging.getLogger(__name__)


class FileManifestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Manifest.objects.all()
    serializer_class = ManifestSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, ManifestPermission]

    def perform_create(self, serializer):
        if "folder" in serializer.validated_data:
            folder = serializer.validated_data["folder"]
            if folder.read_only:
                self.permission_denied(
                    self.request,
                    message="This folder is read-only.",
                )
            serializer.save(permissions=folder.permissions, folder=folder,
                            created_by=self.request.user)
        else:
            self.permission_denied(
                self.request,
                message="A new file manifest cannot be created without specifying a "
                        "folder.",
            )

    def perform_update(self, serializer):
        if "folder" in serializer.validated_data:
            folder = serializer.validated_data["folder"]
            if folder.read_only:
                self.permission_denied(
                    self.request,
                    message="You are trying to move a file to a folder which is "
                            "read-only.",
                )
            if not folder.has_permission(self.request.user, EDIT):
                self.permission_denied(
                    self.request,
                    message="You are trying to move a file. The user does not have "
                            "write access to the target folder.",
                )
        serializer.save()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_local(request, manifest_id: int):
    # Get manifest instance and authorize
    manifest = get_object_or_404(Manifest.objects.for_user(request.user, VIEW), id=manifest_id)
    # 404 if not found or no view permission
    # 403 if no edit permission
    manifest.authorize_user(request.user, EDIT)

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


@extend_schema(
    description="List all manifests in a folder",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Folder ID",
        ),
    ],
    request=None,
    responses=OpenApiTypes.OBJECT,
)
@api_view(["GET"])
def list_manifests(request, pk=None):
    """List all manifests in a folder"""
    obj = get_object_or_404(Folder.objects.for_user(request.user, VIEW), pk=pk)
    return Response({
        manifest.filename: ManifestSerializer(manifest,
                                              context={"request": request}).data
        for manifest in obj
    })
