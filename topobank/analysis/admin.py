from django.contrib import admin  # type: ignore
from django.utils.translation import gettext_lazy as _

from .models import WorkflowResult


class SubjectTypeFilter(admin.SimpleListFilter):
    """Filter for WorkflowResult subject types (Tag, Surface, or Topography)."""

    title = _("Subject Type")
    parameter_name = "subject_type"

    def lookups(self, _request, _model_admin):
        return (
            ("tag", _("Tag")),
            ("surface", _("Surface")),
            ("topography", _("Topography")),
        )

    def queryset(self, _request, queryset):
        value = self.value()
        if value in ("tag", "surface", "topography"):
            filter_key = f"subject_{value}__isnull"
            return queryset.filter(**{filter_key: False})
        return queryset


@admin.register(WorkflowResult)
class WorkflowResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task_state",
        "workflow_name",
        "task_id",
        "subject_type",
        "subject",
        "task_submission_time",
        "task_start_time",
        "task_end_time",
    )
    list_filter = ("task_state", SubjectTypeFilter, "workflow_name")
    ordering = ["-task_start_time"]
    search_fields = ("id", "task_id", "workflow_name")
    search_help_text = "Search by WorkflowResult ID, Task ID, or workflow name"
    actions = ["resubmit_workflows"]

    @admin.display(description="Subject Type")
    def subject_type(self, obj):
        """Display the type of the subject (tag, surface, or topography)."""
        return obj.subject.__class__.__name__

    @admin.action(description="Resubmit selected workflow results")
    def resubmit_workflows(self, request, queryset):
        """Call submit_again() on selected WorkflowResult objects."""
        count = 0
        for workflow_result in queryset:
            workflow_result.submit_again()
            count += 1
        self.message_user(
            request,
            f"Successfully resubmitted {count} workflow result(s).",
        )
