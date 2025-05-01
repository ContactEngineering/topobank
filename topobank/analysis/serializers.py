import logging

from rest_framework import serializers
from rest_framework.reverse import reverse

import topobank.taskapp.serializers

from ..supplib.serializers import StrictFieldMixin
from .models import (
    Analysis,
    AnalysisFunction,
    AnalysisSubject,
    Configuration,
    WorkflowTemplate,
)
from .registry import get_visualization_type

_log = logging.getLogger(__name__)


class ConfigurationSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Configuration
        fields = ["valid_since", "versions"]

    versions = serializers.SerializerMethodField()

    def get_versions(self, obj):
        versions = {}
        for version in obj.versions.all():
            versions[str(version.dependency)] = version.number_as_string()
        return versions


class WorkflowSerializer(
    StrictFieldMixin, serializers.HyperlinkedModelSerializer
):
    class Meta:
        model = AnalysisFunction
        fields = [
            "id",
            "url",
            "name",
            "display_name",
            "visualization_type",
            "kwargs_schema",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:workflow-detail", lookup_field="name", read_only=True
    )

    visualization_type = serializers.SerializerMethodField()

    kwargs_schema = serializers.SerializerMethodField()

    def get_visualization_type(self, obj):
        return get_visualization_type(name=obj.name)

    def get_kwargs_schema(self, obj):
        return obj.get_kwargs_schema()


class SubjectSerializer(
    StrictFieldMixin, serializers.HyperlinkedModelSerializer
):
    class Meta:
        model = AnalysisSubject
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
    class Meta:
        model = Analysis
        fields = [
            "url",
            "id",
            "api",
            "dependencies_url",
            "function",
            "subject",
            "kwargs",
            "task_progress",
            "task_state",
            "task_memory",
            "error",
            "task_traceback",
            "creation_time",
            "start_time",
            "end_time",
            "dois",
            "configuration",
            "duration",
            "folder",
            "name",
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
    error = serializers.CharField(source="get_task_error", read_only=True)

    def get_api(self, obj):
        return {
            "set_name": reverse(
                "analysis:set-name",
                kwargs={"workflow_id": obj.id},
                request=self.context["request"],
            ),
        }

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
        queryset=AnalysisFunction.objects.all(),
        allow_null=True,
    )

    creator = serializers.HyperlinkedRelatedField(
        view_name="users:user-api-detail", read_only=True
    )
