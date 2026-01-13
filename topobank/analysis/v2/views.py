import operator
from functools import reduce

from django.db.models import Q
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
from topobank.authorization.utils import get_user_available_plugins
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
        queryset = Workflow.objects.all().order_by('name')

        # Filter by available plugins when listing workflows
        # Workflow names follow the pattern: plugin_name.workflow.version
        if hasattr(self, 'request') and self.request:
            user = self.request.user
            available_plugins = [app_config.name for app_config in get_user_available_plugins(user)]

            # Always include topobank workflows (e.g., topobank.testing, etc.)
            # in addition to plugin workflows
            queries = [Q(name__startswith="topobank.")]

            if available_plugins:
                # Add Q objects for each plugin to check if workflow name starts with "plugin."
                queries.extend([Q(name__startswith=f"{plugin}.") for plugin in available_plugins])

            if queries:
                queryset = queryset.filter(reduce(operator.or_, queries))
            else:
                queryset = queryset.none()

        return queryset


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

    # Required for schema generation to know that this filter should be exploded.
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='task_state',
                type={'type': 'array', 'items': {'type': 'string'}},
                location=OpenApiParameter.QUERY,
                description='Filter by task state. Can be specified multiple times: task_state=su&task_state=fa',
                required=False,
                explode=True,
                style='form',
                enum=['pe', 'st', 're', 'fa', 'su', 'no']
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

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
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'metadata': {
                        'type': 'object',
                        'description': 'Optional metadata dictionary to store with the analysis',
                        'additionalProperties': True,
                    }
                },
                'example': {
                    'metadata': {
                        'description': 'Analysis for project X',
                        'batch_id': '2024-01-07'
                    }
                }
            }
        },
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
        metadata = request.data.get('metadata')

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
        update_fields = ['updated_by']
        analysis.updated_by = request.user

        # Validate metadata is a dictionary if provided
        if metadata is not None:
            if not isinstance(metadata, dict):
                return Response(
                    {"message": "metadata must be a dictionary"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            analysis.metadata = metadata
            update_fields.append('metadata')

        analysis.save(update_fields=update_fields)
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
