from django_filters.rest_framework import backends
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import topobank.analysis.v1.views as v1
from topobank.analysis.v2.serializers import (
    ConfigurationV2Serializer,
    DependencyV2ListSerializer,
    ResultV2CreateSerializer,
    ResultV2DetailSerializer,
    ResultV2ListSerializer,
    WorkflowV2Serializer,
)
from topobank.authorization.permissions import ObjectPermission, PermissionFilterBackend
from topobank.files.v2.serializers import ManifestV2Serializer
from topobank.supplib.mixins import UserUpdateMixin
from topobank.supplib.pagination import TopobankPaginator

from ..models import Workflow, WorkflowResult
from ..permissions import WorkflowPermissions
from .filters import ResultViewFilterSet, WorkflowViewFilterSet


class ConfigurationView(v1.ConfigurationView):
    serializer_class = ConfigurationV2Serializer


class WorkflowView(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    serializer_class = WorkflowV2Serializer
    permission_classes = [IsAuthenticated, WorkflowPermissions]
    pagination_class = TopobankPaginator
    filter_backends = [backends.DjangoFilterBackend]
    filterset_class = WorkflowViewFilterSet

    def get_queryset(self):
        return Workflow.objects.all()


class ResultView(
    UserUpdateMixin,
    viewsets.ModelViewSet
):
    """
    WorkflowResult ViewSet - Allows CRUD operations on Workflow Results.
    - Retrieve - Get details of a specific workflow result.
    - Destroy - Delete a specific workflow result.
    - List - List all workflow results accessible to the authenticated user.
    - Update - Update details of a specific workflow result.
    - Run - Start an existing workflow result (custom action).
    """

    serializer_class = ResultV2DetailSerializer
    pagination_class = TopobankPaginator
    permission_classes = [IsAuthenticated, ObjectPermission]
    filter_backends = [PermissionFilterBackend, backends.DjangoFilterBackend]
    filterset_class = ResultViewFilterSet

    def get_queryset(self):
        return WorkflowResult.objects.select_related(
            "function",
            "subject_dispatch__tag",
            "subject_dispatch__topography",
            "subject_dispatch__surface",
            "created_by",
            "updated_by",
            "owned_by",
            "permissions",
            "folder",
            "configuration"
        ).order_by("-task_start_time")

    def get_serializer_class(self):
        if self.action == 'list':
            return ResultV2ListSerializer
        elif self.action == 'create':
            return ResultV2CreateSerializer
        else:
            return super().get_serializer_class()

    # Override get_object to specify return type
    def get_object(self) -> WorkflowResult:
        return super().get_object()

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter(
                name='force',
                type=bool,
                location=OpenApiParameter.QUERY,
                description='Force re-run of analysis even if already running or completed',
                required=False,
            ),
        ]
    )
    @action(detail=True, methods=["POST"], url_path="run")
    def run(self, request, *args, **kwargs):
        """Start the analysis task for the given WorkflowResult instance."""
        analysis: WorkflowResult = self.get_object()
        force_submit = request.query_params.get('force', '').lower() in ('true', '1', 'yes')

        # Validation checks
        if analysis.name:
            return Response(
                {"message": "Cannot renew named analysis"},
                status=status.HTTP_403_FORBIDDEN
            )

        if not analysis.subject_dispatch.is_ready():
            return Response(
                {"message": f"{analysis.subject_dispatch.get_type().__name__} subject(s) not ready."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # If already running or completed, reject unless force is set
        if analysis.task_state != WorkflowResult.NOTRUN and not force_submit:
            return Response(
                {
                    "message": "Analysis is already running or completed. "
                               "To re-run, use the force=true query parameter."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # UserUpdateMixin doesnt handle custom actions, so set updated_by manually
        analysis.updated_by = request.user
        analysis.save(update_fields=['updated_by'])
        analysis.submit(force_submit=force_submit)

        serializer = self.get_serializer(analysis, context={'request': request})
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None)
    @action(detail=True, methods=['GET'], url_path="dependencies", url_name="dependency")
    def dependencies(self, request, *args, **kwargs):
        """Get dependencies for the WorkflowResult"""
        analysis: WorkflowResult = self.get_object()
        serializer = DependencyV2ListSerializer(analysis.dependencies, context={'request': request})

        # Get the serialized data (a list)
        data = serializer.data

        # Paginate the list (Have to do this manually since this is a custom action)
        paginator = self.pagination_class()
        paginated_data = paginator.paginate_queryset(data, request, view=self)

        # Return paginated response
        return paginator.get_paginated_response(paginated_data)

    @extend_schema(request=None)
    @action(detail=True, methods=['GET'], url_path="files", url_name="folder")
    def list_manifests(self, request, *args, **kwargs):
        """Get the folder of the WorkflowResult"""
        analysis: WorkflowResult = self.get_object()
        folder = analysis.folder
        if folder is None:
            return Response(
                {"message": "This analysis does not have a folder."},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response({
            manifest.filename: ManifestV2Serializer(manifest,
                                                    context={"request": request}).data
            for manifest in folder.files.all()
        })
