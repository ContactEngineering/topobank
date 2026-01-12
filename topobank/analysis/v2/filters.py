from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django_filters.rest_framework import FilterSet, filters
from drf_spectacular.utils import OpenApiTypes, extend_schema_field

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.manager.models import Surface, Tag, Topography
from topobank.taskapp.utils import TASK_STATE_CHOICES

APP_CHOICES = [
    (app_config.name, app_config.verbose_name)
    for app_config in apps.get_app_configs()
    if app_config.name in settings.PLUGIN_MODULES
    and app_config.name not in getattr(settings, 'EXCLUDED_PLUGIN_CHOICES', [])
]


class WorkflowViewFilterSet(FilterSet):
    """
    FilterSet for Workflow model.

    Filters:
    - name: Filter by workflow name (case-insensitive contains)
    - display_name: Filter by display name (case-insensitive contains)
    - app: Filter by app/plugin name (checks if user has access to plugin)
    - subject_type: Filter by subject type they can process (tag, surface, topography)
    """

    name = filters.CharFilter(lookup_expr="icontains")
    display_name = filters.CharFilter(lookup_expr="icontains")
    app = filters.ChoiceFilter(choices=APP_CHOICES, method="filter_app")
    subject_type = filters.ChoiceFilter(
        method="filter_subject_type",
        choices=[("tag", "Tag"), ("surface", "Surface"), ("topography", "Topography")]
    )

    class Meta:
        model = Workflow
        fields = ["name", "display_name", "app", "subject_type"]

    def filter_app(self, queryset, name, value):
        """
        Filter workflows by app/plugin name.

        Args:
            queryset: Initial queryset
            name: Filter field name
            value: App/plugin name to filter by

        Returns:
            Filtered queryset or empty queryset if app not found
        """
        if value in dict(APP_CHOICES):
            return queryset.filter(name__icontains=value)

        return queryset.none()

    def filter_subject_type(self, queryset, name, value):
        """
        Filter workflows by subject type they can process.

        Args:
            queryset: Initial queryset
            name: Filter field name
            value: Subject type to filter by ("tag", "surface", "topography")

        Returns:
            Filtered queryset
        """
        match value.lower():
            case "tag":
                model_class = Tag
            case "surface":
                model_class = Surface
            case "topography":
                model_class = Topography
            case _:
                return queryset.none()

        workflow_ids = [
            workflow.id
            for workflow in queryset
            if workflow.has_implementation(model_class)
        ]
        return queryset.filter(id__in=workflow_ids)


class ResultViewFilterSet(FilterSet):
    """
    FilterSet for WorkflowResult model.

    Filters:
    - task_state: Filter by task execution state
    - created_gte: Results created on or after this datetime
    - created_lte: Results created on or before this datetime
    - workflow_name: Filter by workflow name (case-insensitive contains)
    - subject_id: Filter by subject ID (works for tag, surface, or topography)
    - subject_type: Filter by subject type (tag, surface, or topography)
    - tag: Filter by tag name (case-insensitive contains)
    - named: Boolean - True for named analyses, False for unnamed
    """

    task_state = filters.MultipleChoiceFilter(
        choices=TASK_STATE_CHOICES,
        help_text="Filter by task state. Can be specified multiple times: task_state=su&task_state=fa"
    )

    # Filter by creation time on or after (greater than or equal)
    created_gte = filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
        label="Created on or after"
    )
    # Filter by creation time on or before (less than or equal)
    created_lte = filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
        label="Created on or before"
    )

    # Filter by workflow name
    workflow_name = filters.CharFilter(
        field_name="function__name",
        lookup_expr="icontains",
        label="Workflow name"
    )

    # Filtering by multiple subject IDs
    subject_ids = filters.BaseInFilter(method="filter_subject_ids")

    # Support combined filtering: subject_id + subject_type
    subject_id = filters.NumberFilter(method="filter_subject_id")
    subject_type = filters.ChoiceFilter(
        method="filter_subject_type_with_id",
        choices=[("tag", "Tag"), ("surface", "Surface"), ("topography", "Topography")]
    )

    subject_name = filters.CharFilter(method="filter_subject_name")

    # Filter by tag name
    tag = filters.CharFilter(method="filter_tag_name")

    # Named/unnamed filter
    named = filters.BooleanFilter(method="filter_named")

    class Meta:
        model = WorkflowResult
        fields = [
            "task_state",
            "created_gte",
            "created_lte",
            "workflow_name",
            "subject_id",
            "subject_ids",
            "subject_name",
            "tag",
            "subject_type",
            "named"
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def filter_subject_ids(self, queryset, name, value):
        """
        Filter by multiple subject IDs across all subject types.

        Usage: ?subject_ids=1,2,3
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(subject_dispatch__tag_id__in=value)
            | Q(subject_dispatch__topography_id__in=value)
            | Q(subject_dispatch__surface_id__in=value)
        )

    def filter_subject_id(self, queryset, name, value):
        """Filter by subject ID - stores for use with subject_type filter."""
        # Store the subject_id for combined filtering
        self._subject_id = value

        # If subject_type is also specified, filtering will happen there
        if "subject_type" not in self.data:
            # No subject_type specified, search across all types
            return queryset.filter(
                Q(subject_dispatch__tag_id=value)
                | Q(subject_dispatch__topography_id=value)
                | Q(subject_dispatch__surface_id=value)
            )

        return queryset

    def filter_subject_type_with_id(self, queryset, name, value):
        """
        Filter by subject type, optionally combined with subject_id.

        If both subject_id and subject_type are provided, filters by that specific combination.
        If only subject_type is provided, filters by type only.
        """
        subject_id = getattr(self, "_subject_id", None)

        match value.lower():
            case "tag":
                q = Q(subject_dispatch__tag__isnull=False)
                if subject_id:
                    q &= Q(subject_dispatch__tag_id=subject_id)
                return queryset.filter(q)
            case "surface":
                q = Q(subject_dispatch__surface__isnull=False)
                if subject_id:
                    q &= Q(subject_dispatch__surface_id=subject_id)
                return queryset.filter(q)
            case "topography":
                q = Q(subject_dispatch__topography__isnull=False)
                if subject_id:
                    q &= Q(subject_dispatch__topography_id=subject_id)
                return queryset.filter(q)
            case _:
                return queryset.none()

    def filter_subject_name(self, queryset, name, value):
        """
        Filter by subject name (case-insensitive contains).

        Args:
            queryset: Initial queryset
            name: Filter field name
            value: Subject name to filter by

        Returns:
            Filtered queryset
        """
        return queryset.filter(
            Q(subject_dispatch__tag__name__icontains=value)
            | Q(subject_dispatch__surface__name__icontains=value)
            | Q(subject_dispatch__topography__name__icontains=value)
        )

    def filter_tag_name(self, queryset, name, value):
        """
        Filter by tag name (case-insensitive contains).

        Args:
            queryset: Initial queryset
            name: Filter field name
            value: Tag name to filter by

        Returns:
            Filtered queryset
        """
        return queryset.filter(subject_dispatch__tag__name__icontains=value)

    def filter_named(self, queryset, name, value):
        """
        Filter by whether the analysis has a name (is saved).

        Args:
            queryset: Initial queryset
            name: Filter field name
            value: True for named analyses, False for unnamed

        Returns:
            Filtered queryset
        """
        if value:
            return queryset.filter(name__isnull=False)
        return queryset.filter(name__isnull=True)
