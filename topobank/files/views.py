from django.shortcuts import get_object_or_404
from rest_framework import mixins
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from topobank.files.file_upload import FileUploadService

from .models import Manifest
from .permissions import FileManifestObjectPermissions
from .serializers import FileManifestSerializer, FileUploadSerializer


class FileManifestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Manifest.objects.all()
    serializer_class = FileManifestSerializer
    permission_classes = [FileManifestObjectPermissions]


class FileDirectUploadStartApi(APIView):

    # ToDo Permissions and Auth
    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = FileUploadService(request.user)
        presigned_data = service.start(**serializer.validated_data)
        return Response(data=presigned_data)


class FileDirectUploadFinishApi(APIView):

    class InputSerializer(drf_serializers.Serializer):
        file_id = drf_serializers.CharField()

    # ToDo Permissions and Auth
    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_id = serializer.validated_data["file_id"]
        service = FileUploadService(request.user)
        file_manifest = get_object_or_404(Manifest, id=file_id)
        service.finish(file_manifest=file_manifest)
        return Response({"id": file_id})


class FileDirectUploadLocalApi(APIView):
    def post(self, request, file_id):
        file_manifest = get_object_or_404(Manifest, id=file_id)
        file = request.FILES["file"]
        service = FileUploadService(request.user)
        file = service.upload_local(file_manifest=file_manifest, file=file)

        return Response({"id": file_id})
