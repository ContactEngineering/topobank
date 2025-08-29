from django.contrib import admin  # type: ignore

from .models import AnalysisSubject, Workflow, WorkflowResult


@admin.register(WorkflowResult)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task_state",
        "task_id",
        "function",
        "subject_dispatch",
        "task_submission_time",
        "task_start_time",
        "task_end_time",
    )
    list_filter = ("task_state", "function")
    ordering = ["-task_start_time"]


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "display_name")
    ordering = ["id"]


@admin.register(AnalysisSubject)
class AnalysisSubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'tag', 'surface', 'topography')
    ordering = ['id']
