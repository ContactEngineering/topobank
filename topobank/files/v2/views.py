import logging

from django_filters.rest_framework import backends
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from topobank.authorization.permissions import EDIT, PermissionFilterBackend
from topobank.supplib.mixins import UserUpdateMixin
from topobank.supplib.pagination import TopobankPaginator

from ..models import Manifest
from ..permissions import ManifestPermission
from .serializers import ManifestV2CreateSerializer, ManifestV2Serializer

_log = logging.getLogger(__name__)


class FileManifestViewSet(
    UserUpdateMixin,
    viewsets.ModelViewSet,
):
    """v2 ViewSet for Manifest model."""
    queryset = Manifest.objects.all()
    serializer_class = ManifestV2Serializer
    permission_classes = [IsAuthenticatedOrReadOnly, ManifestPermission]
    filter_backends = [PermissionFilterBackend, backends.DjangoFilterBackend]
    pagination_class = TopobankPaginator

    def get_serializer_class(self):
        if self.action == "create":
            return ManifestV2CreateSerializer
        return ManifestV2Serializer

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
