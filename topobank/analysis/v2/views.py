import operator
from functools import reduce

from django.db import transaction
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
)
from topobank.authorization.permissions import ObjectPermission, PermissionFilterBackend
from topobank.authorization.utils import get_user_available_plugins
from topobank.files.v2.serializers import ManifestV2Serializer
from topobank.supplib.mixins import UserUpdateMixin
from topobank.supplib.pagination import TopobankPaginator

from ..models import Configuration, Workflow, WorkflowResult
from ..permissions import WorkflowPermissions
from ..serializers import WorkflowDetailSerializer, WorkflowListSerializer
from .filters import ResultViewFilterSet, WorkflowViewFilterSet


class ConfigurationView(v1.ConfigurationView):
    queryset = Configuration.objects.prefetch_related("versions")
    serializer_class = ConfigurationV2Serializer


class WorkflowView(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    serializer_class = WorkflowDetailSerializer
    permission_classes = [IsAuthenticated, WorkflowPermissions]
    pagination_class = TopobankPaginator
    filter_backends = [backends.DjangoFilterBackend]
    filterset_class = WorkflowViewFilterSet

    def get_serializer_class(self):
        if self.action == "list":
            return WorkflowListSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = Workflow.objects.all().order_by('name')

        # Filter by available plugins when listing workflows
        # Workflow names follow the pattern: plugin_name.workflow.version
        if hasattr(self, 'request') and self.request:
            user = self.request.user

            # Cache available plugins on the user object for this request
            if not hasattr(user, '_cached_available_plugins'):
                user._cached_available_plugins = [
                    app_config.name for app_config in get_user_available_plugins(user)
                ]
            available_plugins = user._cached_available_plugins

            # Always include topobank workflows (e.g., topobank.testing, etc.)
            # in addition to plugin workflows
            queries = [Q(name__startswith="topobank.")]

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

    def list(self, request, *args, **kwargs):
        """Override list to initialize permission cache for performance"""
        if request.user.is_authenticated:
            # Cache user groups once per request
            if not hasattr(request.user, '_cached_group_ids'):
                request.user._cached_group_ids = list(
                    request.user.groups.values_list('id', flat=True)
                )
        return super().list(request, *args, **kwargs)


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
        # PermissionFilterBackend handles permission filtering with two-step optimization
        # We just apply business logic filters and optimizations here
        qs = WorkflowResult.objects.select_related(
            "function",
            "subject_dispatch__tag",
            "subject_dispatch__topography",
            "subject_dispatch__surface",
            "created_by",
            "updated_by",
            "permissions",
        )

        # Optimize prefetching based on action to reduce unnecessary data loading
        if self.action == 'list':
            # List view: minimal data needed
            qs = qs.prefetch_related(
                'permissions__user_permissions',
                'permissions__organization_permissions',
            ).defer(
                # Defer large JSONFields not displayed in list serializer
                'kwargs',        # Not shown in list view
                'metadata',      # Not shown in list view
            )
        else:
            # Detail/update/delete views: fetch complete data
            qs = qs.select_related(
                "owned_by",
                "folder",
                "configuration",
            ).prefetch_related(
                'permissions__user_permissions__user',
                'permissions__organization_permissions__organization',
                'configuration__versions',
            )

        return qs.order_by("-task_start_time")

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
        """Override list to initialize permission cache for performance"""
        # Initialize cache on user object to avoid repeated queries during serialization
        if request.user.is_authenticated:
            # Cache user groups once per request
            if not hasattr(request.user, '_cached_group_ids'):
                request.user._cached_group_ids = list(
                    request.user.groups.values_list('id', flat=True)
                )
        return super().list(request, *args, **kwargs)

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
    @transaction.non_atomic_requests
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

        # TO DISCUSS: `is_ready` means the topography has been processed and metadata extracted and stored
        # to the database, but the workflows can run before this has happened by directly opening the raw
        # data file. If a file is not readable, the workflows will fail.
        # if not analysis.subject_dispatch.is_ready():
        #     return Response(
        #         {"message": f"{analysis.subject_dispatch.get_type().__name__} subject(s) not ready."},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )

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
        update_fields = ['updated_by']

        # Validate metadata is a dictionary if provided
        if metadata is not None:
            if not isinstance(metadata, dict):
                return Response(
                    {"message": "metadata must be a dictionary"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            analysis.metadata = metadata
            update_fields.append('metadata')

        # Wrap DB writes and task submission in transaction
        with transaction.atomic():
            analysis.save(update_fields=update_fields)
            analysis.submit(force_submit=force_submit)

        serializer = self.get_serializer(analysis, context={'request': request})
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None)
    @action(detail=True, methods=['GET'], url_path="dependencies", url_name="dependency")
    def dependencies(self, request, *args, **kwargs):
        """Get dependencies for the WorkflowResult"""
        analysis: WorkflowResult = self.get_object()
        dependencies_dict = analysis.dependencies

        if not dependencies_dict:
            paginator = self.pagination_class()
            paginator.paginate_queryset([], request, view=self)
            return paginator.get_paginated_response([])

        # Get paginator
        paginator = self.pagination_class()

        # Get workflow result IDs and create an ordered list for pagination
        # The dependencies dict maps subject_id -> workflow_result_id
        workflow_result_ids = list(dependencies_dict.values())

        # Paginate the IDs list first (before fetching/serializing)
        page_ids = paginator.paginate_queryset(workflow_result_ids, request, view=self)

        # Create a filtered dependencies dict with only the page items
        page_ids_set = set(page_ids)
        paginated_deps = {k: v for k, v in dependencies_dict.items() if v in page_ids_set}

        # Use the serializer to handle fetching and serialization (with optimized queries)
        serializer = DependencyV2ListSerializer(paginated_deps, context={'request': request})
        page_data = serializer.data

        # Return paginated response
        return paginator.get_paginated_response(page_data)

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

        # Prefetch related users to avoid N+1 queries
        manifests = folder.files.select_related('created_by', 'updated_by').all()

        return Response({
            manifest.filename: ManifestV2Serializer(manifest,
                                                    context={"request": request}).data
            for manifest in manifests
        })

    @transaction.atomic
    def perform_destroy(self, instance):
        return super().perform_destroy(instance)

    @transaction.atomic
    def perform_update(self, serializer):
        return super().perform_update(serializer)

    @transaction.atomic
    def perform_create(self, serializer):
        return super().perform_create(serializer)
