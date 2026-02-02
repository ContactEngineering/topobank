from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

import topobank.taskapp.serializers

from ..manager.models import Surface, Tag, Topography
from ..supplib.mixins import StrictFieldMixin
from ..supplib.serializers import UserField
from .models import (
    Configuration,
    Workflow,
    WorkflowResult,
    WorkflowSubject,
    WorkflowTemplate,
)


class ConfigurationSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    """Serializer for Configuration model."""
    class Meta:
        model = Configuration
        fields = ["valid_since", "versions"]

    versions = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_versions(self, obj):
        versions = {}
        for version in obj.versions.all():
            versions[str(version.dependency)] = version.number_as_string()
        return versions


class WorkflowListSerializer(
    StrictFieldMixin, serializers.HyperlinkedModelSerializer
):
    """Serializer for Workflow model."""
    class Meta:
        model = Workflow
        fields = [
            "url",
            "name",
            "display_name",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:workflow-detail", lookup_field="name", read_only=True
    )


class WorkflowDetailSerializer(
    StrictFieldMixin, serializers.HyperlinkedModelSerializer
):
    """Serializer for Workflow model."""
    class Meta:
        model = Workflow
        fields = [
            "url",
            "name",
            "display_name",
            "subject_types",
            "kwargs_schema",
            "outputs_schema",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:workflow-detail", lookup_field="name", read_only=True
    )

    subject_types = serializers.SerializerMethodField()

    kwargs_schema = serializers.SerializerMethodField()

    outputs_schema = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_subject_types(self, obj):
        subject_types = []
        if obj.has_implementation(Surface):
            subject_types.append("surface")
        if obj.has_implementation(Topography):
            subject_types.append("topography")
        if obj.has_implementation(Tag):
            subject_types.append("tag")
        return subject_types

    @extend_schema_field(serializers.DictField())
    def get_kwargs_schema(self, obj):
        return obj.get_kwargs_schema()

    @extend_schema_field(serializers.ListField())
    def get_outputs_schema(self, obj):
        return obj.get_outputs_schema()


class SubjectSerializer(
    StrictFieldMixin, serializers.HyperlinkedModelSerializer
):
    """Serializer for WorkflowSubject model."""
    class Meta:
        model = WorkflowSubject
        fields = ["id", "tag", "topography", "surface"]

    tag = serializers.HyperlinkedRelatedField(
        view_name="manager:tag-api-detail", read_only=True, lookup_field="name"
    )
    topography = serializers.HyperlinkedRelatedField(
        view_name="manager:topography-api-detail", read_only=True
    )
    surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail", read_only=True
    )


class ResultSerializer(
    StrictFieldMixin, topobank.taskapp.serializers.TaskStateModelSerializer
):
    """Serializer for WorkflowResult model."""
    class Meta:
        model = WorkflowResult
        fields = [
            "url",
            "id",
            "api",
            "dependencies_url",
            "function",
            "subject",
            "kwargs",
            "creation_time",
            "task_state",
            "task_progress",
            "task_messages",  # Informative message on the progress of the task
            "task_memory",
            "task_error",
            "task_traceback",
            "task_submission_time",
            "task_start_time",
            "task_end_time",
            "task_duration",
            "task_id",
            "launcher_task_id",
            "dois",
            "configuration",
            "folder",
            "name",
            "creator"
        ]
        read_only_fields = fields

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:result-detail", read_only=True
    )
    dependencies_url = serializers.SerializerMethodField()
    api = serializers.SerializerMethodField()
    function = serializers.HyperlinkedRelatedField(
        view_name="analysis:workflow-detail", lookup_field="name", read_only=True
    )
    subject = SubjectSerializer(source="subject_dispatch", read_only=True)
    folder = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    configuration = serializers.HyperlinkedRelatedField(
        view_name="analysis:configuration-detail", read_only=True
    )
    creation_time = serializers.DateTimeField(source="created_at", read_only=True)
    creator = UserField(source="created_by", read_only=True)

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "set_name": {"type": "string"},
            },
            "required": ["set_name"],
        }
    )
    def get_api(self, obj: WorkflowResult) -> dict:
        return {
            "set_name": reverse(
                "analysis:set-name",
                kwargs={"workflow_id": obj.id},
                request=self.context["request"],
            ),
        }

    @extend_schema_field(serializers.URLField())
    def get_dependencies_url(self, obj):
        return reverse(
            "analysis:dependencies",
            kwargs={"workflow_id": obj.id},
            request=self.context["request"],
        )


class WorkflowTemplateSerializer(
    StrictFieldMixin, serializers.HyperlinkedModelSerializer
):
    class Meta:
        model = WorkflowTemplate
        fields = [
            "id",
            "name",
            "kwargs",
            "implementation",
            "creator",
        ]

    implementation = serializers.HyperlinkedRelatedField(
        view_name="analysis:workflow-detail",
        lookup_field="name",
        queryset=Workflow.objects.all(),
        allow_null=True,
    )

    creator = serializers.HyperlinkedRelatedField(
        view_name="users:user-v1-detail", read_only=True
    )
