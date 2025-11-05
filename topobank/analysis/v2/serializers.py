from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.reverse import reverse

from topobank.organizations.models import Organization
import topobank.taskapp.serializers as taskapp_serializers
from topobank.analysis.models import Configuration, Workflow, WorkflowResult, WorkflowSubject
from topobank.manager.models import Surface, Tag, Topography
from topobank.supplib.serializers import (
    ModelRelatedField,
    OrganizationField,
    PermissionsField,
    StrictFieldMixin,
    StringOrIntegerField,
    SubjectField,
    UserField,
)


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
    serializers.ModelSerializer
):
    class Meta:
        model = Workflow
        fields = [
            "id",
            "url",
            "name",
            "display_name",
        ]
        read_only_fields = fields

    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:workflow-v2-detail", read_only=True
    )


class ResultCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowResult
        required_fields = [
            "function",
            "subject",
            "subject_type",
        ]
        fields = required_fields + [
            "kwargs",
        ]

    function = serializers.IntegerField()
    subject = StringOrIntegerField()
    subject_type = serializers.CharField()

    def create(self, validated_data: dict) -> WorkflowResult:
        workflow = validated_data.pop("function")
        user = self.context["request"].user

        instance = WorkflowResult.objects.create(
            created_by=user,
            updated_by=user,
            owned_by=Organization.objects.for_user(user).first(),  # TODO: Limit to one organization per user
            function=workflow,
            subject_dispatch=WorkflowSubject.objects.create(validated_data.pop("subject")),
            kwargs=validated_data.get("kwargs", {}),
            task_state=WorkflowResult.NOTRUN
        )
        instance.grant_permission(user, "edit")

        # Return the created WorkflowResult instance
        return instance

    def validate_function(self, value):
        """Validate that the workflow exists and return the instance"""
        try:
            value = Workflow.objects.get(id=value)
        except Workflow.DoesNotExist:
            raise serializers.ValidationError({"function": "Workflow with given ID does not exist."})
        return value

    def validate_subject_type(self, value):
        """Validate and normalize the subject type to lowercase"""
        value = value.lower()
        if value not in ["surface", "tag", "topography"]:
            raise serializers.ValidationError(
                {"subject_type": "Subject type must be either 'surface', 'tag', or 'topography'."}
            )
        return value

    def validate(self, data):
        """
        Validate that the subject exists and user has permission to access it.
        Replace the subject ID/name with the actual instance for use in create().
        """
        subject_value = data["subject"]
        subject_type = data["subject_type"]
        user = self.context["request"].user
        not_found_error_msg = "does not exist or you lack permission to access it."

        match subject_type:
            case "surface":
                # Surface requires integer ID
                try:
                    subject_id = int(subject_value)
                except (ValueError, TypeError):
                    raise serializers.ValidationError({
                        "subject": "Surface subject must be an integer ID."
                    })

                try:
                    # Verify surface exists and user has permission
                    data["subject"] = Surface.objects.for_user(user).get(id=subject_id)
                except Surface.DoesNotExist:
                    raise serializers.ValidationError({
                        "subject": f"Surface '{subject_value}' {not_found_error_msg}."
                    })

            case "topography":
                # Topography requires integer ID
                try:
                    subject_id = int(subject_value)
                except (ValueError, TypeError):
                    raise serializers.ValidationError({
                        "subject": "Topography subject must be an integer ID."
                    })

                try:
                    # Verify topography exists and user has permission
                    data["subject"] = Topography.objects.for_user(user).get(id=subject_id)
                except Topography.DoesNotExist:
                    raise serializers.ValidationError({
                        "subject": f"Topography '{subject_value}' {not_found_error_msg}."
                    })

            case "tag":
                # Tag accepts: integer ID or string name
                tag = None

                # Try as integer ID first
                if isinstance(subject_value, int) or (isinstance(subject_value, str) and subject_value.isdigit()):
                    try:
                        tag_id = int(subject_value)
                        tag = Tag.objects.get(id=tag_id)
                    except Tag.DoesNotExist:
                        raise serializers.ValidationError({
                            "subject": f"Tag '{tag_id}' {not_found_error_msg}."
                        })
                else:
                    # Try as tag name
                    try:
                        tag = Tag.objects.get(name=subject_value)
                    except Tag.DoesNotExist:
                        raise serializers.ValidationError({
                            "subject": f"Tag '{subject_value}' {not_found_error_msg}."
                        })

                # Authorize tag for user (tags only support "view" permission)
                try:
                    tag.authorize_user(user, "view")
                except PermissionDenied as e:
                    raise serializers.ValidationError({
                        "subject": f"Tag '{subject_value}' {not_found_error_msg}."
                    })

                # Verify tag has accessible surfaces
                if tag.get_related_surfaces().count() == 0:
                    raise serializers.ValidationError({
                        "subject": f"Tag '{subject_value}' has no accessible surfaces."
                    })

                data["subject"] = tag

        return data


class ResultListSerializer(
    taskapp_serializers.TaskStateModelSerializer,
):
    class Meta:
        model = WorkflowResult
        fields = [
            "id",
            "url",
            "function",
            "subject",
            "created_at",
            "updated_at",
            "name",
            "created_by",
            "updated_by",
            "permissions"
        ]
        task_state_fields = [
            "task_state",
            "task_progress",
        ]
        fields += task_state_fields
        read_only_fields = fields

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:result-v2-detail", read_only=True
    )
    function = WorkflowSerializer(
        read_only=True
    )
    created_by = UserField(read_only=True)
    updated_by = UserField(read_only=True)
    permissions = PermissionsField(read_only=True)
    subject = SubjectField(read_only=True)


class ResultDetailSerializer(
    StrictFieldMixin, taskapp_serializers.TaskStateModelSerializer
):
    class Meta:
        model = WorkflowResult
        task_state_fields = [
            "task_state",
            "task_progress",
            "task_messages",
            "task_memory",
            "task_error",
            "task_traceback",
            "task_submission_time",
            "task_start_time",
            "task_end_time",
            "task_duration",
            "task_id",
            "launcher_task_id",
        ]
        read_only_fields = [
            "id",
            "url",
            "dependencies",
            "function",
            "subject",
            "kwargs",
            "created_at",
            "updated_at",
            "dois",
            "configuration",
            "folder",
            "created_by",
            "updated_by",
            "owned_by",
            "permissions"
        ] + task_state_fields
        # Name can be changed by the user
        fields = read_only_fields + ["name", "description"]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="analysis:result-v2-detail", read_only=True
    )
    function = WorkflowSerializer(
        read_only=True
    )
    folder = ModelRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    configuration = ModelRelatedField(
        view_name="analysis:configuration-v2-detail", read_only=True
    )
    created_by = UserField(read_only=True)
    updated_by = UserField(read_only=True)
    owned_by = OrganizationField(read_only=True)
    permissions = PermissionsField(read_only=True)
    subject = SubjectField(read_only=True)
    dependencies = serializers.SerializerMethodField()

    def get_dependencies(self, obj: WorkflowResult):
        ret = {
            "count": len(obj.dependencies.items()),
            "url": reverse("analysis:result-v2-deps", kwargs={"pk": obj.id})
        }
        return ret


class DependencyListSerializer(serializers.Serializer):
    """
    Serializer for WorkflowResult dependencies.

    Transforms a dictionary mapping subject IDs to WorkflowResult IDs into a paginated
    response with count and results. Subject IDs are discarded during serialization.

    Input:
        dict: {subject_id: workflow_result_id, ...}

    Output:
        dict: {
            "count": int,
            "results": [{"id": int, "url": str, "task_state": str}, ...]
        }

    Note:
        Uses bulk querying to avoid N+1 database queries when fetching multiple
        WorkflowResult objects. Missing WorkflowResults are silently excluded.
    """

    def to_representation(self, data: dict):
        """Convert the dependencies dict to a dict with count and results list"""
        if not data:
            return {
                "count": 0,
                "results": []
            }

        # Get all workflow result IDs at once to avoid N+1 queries
        workflow_result_ids = list(data.values())
        workflow_results = WorkflowResult.objects.filter(id__in=workflow_result_ids).in_bulk()

        dependencies_list = []
        for subject_id, workflow_result_id in data.items():
            dep_wr = workflow_results.get(workflow_result_id)
            if dep_wr:
                dependencies_list.append({
                    "id": workflow_result_id,
                    "url": reverse("analysis:result-v2-detail", kwargs={"pk": workflow_result_id},
                                   request=self.context.get("request")),
                    "task_state": dep_wr.task_state,
                })

        return {
            "count": len(dependencies_list),
            "results": dependencies_list
        }
