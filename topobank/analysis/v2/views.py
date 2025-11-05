from django_filters.rest_framework import backends
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from topobank.analysis.v2.serializers import (
    ConfigurationSerializer,
    ResultCreateSerializer,
    ResultDetailSerializer,
    ResultListSerializer,
    WorkflowSerializer,
    DependencyListSerializer
)
from topobank.authorization.permissions import METHOD_TO_PERM, ObjectPermission, PermissionFilterBackend
from topobank.supplib.pagination import TopobankPaginator
import topobank.analysis.v1.views as v1

from ..models import Workflow, WorkflowResult
from ..permissions import WorkflowPermissions
from .filters import ResultViewFilterSet, WorkflowViewFilterSet


class ConfigurationView(v1.ConfigurationView):
    serializer_class = ConfigurationSerializer


class WorkflowView(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    serializer_class = WorkflowSerializer
    permission_classes = [WorkflowPermissions, IsAuthenticated]
    filter_backends = [backends.DjangoFilterBackend]
    filterset_class = WorkflowViewFilterSet

    def get_queryset(self):
        return Workflow.objects.all()


class ResultView(
    viewsets.GenericViewSet,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin
):
    """
    WorkflowResult ViewSet - Allows CRUD operations on Workflow Results.
    - Retrieve - Get details of a specific workflow result.
    - Destroy - Delete a specific workflow result.
    - List - List all workflow results accessible to the authenticated user.
    - Update - Update details of a specific workflow result.
    - Renew - Renew an existing workflow result (custom action).
    """

    serializer_class = ResultDetailSerializer
    pagination_class = TopobankPaginator
    permission_classes = [ObjectPermission, IsAuthenticated]
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
            return ResultListSerializer
        elif self.action == 'create':
            return ResultCreateSerializer
        else:
            return ResultDetailSerializer

    def get_permission_level(self):
        if self.action == 'renew':
            return 'view'  # Assuming renew requires view permission
        return METHOD_TO_PERM.get(self.request.method)
    
    # Override get_object to specify return type
    def get_object(self) -> WorkflowResult:
        return super().get_object()

    @extend_schema(request=ResultCreateSerializer,
                   responses={201: ResultDetailSerializer})
    def create(self, request, *args, **kwargs):
        """Submit new analysis (POST). Submits a new workflow analysis (WorkflowResult) based on the provided data."""
        serializer = self.get_serializer(data=request.data, context={'request': request})

        serializer.is_valid(raise_exception=True)
        # Serializer validation checks if user has permission to access the subject(s)
        analysis = serializer.save()

        output_serializer = ResultDetailSerializer(analysis, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


    @extend_schema(request=None)
    @action(detail=True, methods=["PUT"], url_path="run")
    def run(self, request, *args, **kwargs):
        """Start the analysis task for the given WorkflowResult instance."""
        analysis: WorkflowResult = self.get_object()
        force_submit = request.query_params.get('force', 'false').lower() == 'true'
        task_state = analysis.task_state
        
        if analysis.name:
            return Response({"message": "Cannot renew named analysis"},
                            status=status.HTTP_403_FORBIDDEN)
        if not analysis.subject_dispatch.is_ready():
            return Response(
                {"message": f"{analysis.subject_dispatch.get_type().__name__} subject(s) not ready."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if task_state == WorkflowResult.NOTRUN:
            analysis.updated_by = request.user
            analysis.submit()
        elif not force_submit:
            return Response(
                {"message": "Analysis is already running or completed. To re-run, use the force=True parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            analysis.updated_by = request.user
            analysis.submit_again(force_submit=True)

        serializer = self.get_serializer(analysis, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @extend_schema(request=None)
    @action(detail=True, methods=['GET'], url_path="dependencies", url_name="deps")
    def dependencies(self, request, *args, **kwargs):
        """Get dependencies for the WorkflowResult"""
        analysis: WorkflowResult = self.get_object()
        serializer = DependencyListSerializer(analysis.dependencies, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
