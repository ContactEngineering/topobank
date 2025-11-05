from django.contrib import admin  # type: ignore
from django.urls import reverse
from django.utils.html import format_html

from .models import Workflow, WorkflowResult, WorkflowSubject

from django.utils.translation import gettext_lazy as _

def create_null_filter(field_name, filter_title):
    """
    Factory function to create a null/not-null filter for a given field.

    Parameters
    ----------
    field_name: str
        The name of the field to filter on.

    filter_title: str
        The display title of the filter.

    Returns
    -------
    NullFilter:
        A django.contrib.admin.SimpleListFilter subclass.

    Usage
    -----
        YourFilter = create_null_filter('your_field_name', 'Your Filter Title')

    Examples
    --------
        TagFilter = create_null_filter('tag', 'Tag')
        SurfaceFilter = create_null_filter('surface', 'Surface')
        TopographyFilter = create_null_filter('topography', 'Topography')
    """
    class NullFilter(admin.SimpleListFilter):
        title = filter_title
        parameter_name = f'{field_name}__isnull'

        def lookups(self, _request, _model_admin):
            return (
                ('false', _('Has value')),
                ('true', _('Is empty')),
            )

        def queryset(self, _request, queryset):
            if self.value() == 'false':
                return queryset.filter(**{self.parameter_name: False})
            if self.value() == 'true':
                return queryset.filter(**{self.parameter_name: True})
            return queryset

    return NullFilter


TagFilter = create_null_filter('tag', 'Tag')
SurfaceFilter = create_null_filter('surface', 'Surface')
TopographyFilter = create_null_filter('topography', 'Topography')


class SubjectTypeFilter(admin.SimpleListFilter):
    """Filter for WorkflowResult subject types (Tag, Surface, or Topography)."""
    title = _('Subject Type')
    parameter_name = 'subject_type'

    def lookups(self, _request, _model_admin):
        return (
            ('tag', _('Tag')),
            ('surface', _('Surface')),
            ('topography', _('Topography')),
        )

    def queryset(self, _request, queryset):
        value = self.value()
        if value in ('tag', 'surface', 'topography'):
            filter_key = f'subject_dispatch__{value}__isnull'
            return queryset.filter(**{filter_key: False})
        return queryset


@admin.register(WorkflowResult)
class WorkflowResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task_state",
        "function__display_name",
        "task_id",
        "subject_type",
        "subject",
        "task_submission_time",
        "task_start_time",
        "task_end_time",
    )
    list_filter = ("task_state", SubjectTypeFilter, "function__display_name")
    ordering = ["-task_start_time"]
    search_fields = ("id", "task_id")
    search_help_text = "Search by WorkflowResult ID or Task ID"
    actions = ["resubmit_workflows"]

    @admin.display(description='Subject Type')
    def subject_type(self, obj):
        """Display the type of the subject (tag, surface, or topography)."""
        return obj.subject.__class__.__name__

    @admin.action(description='Resubmit selected workflow results')
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


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "display_name")
    ordering = ["id"]
    search_fields = ("name", "display_name")
    search_help_text = "Search by Workflow name or display name"


@admin.register(WorkflowSubject)
class AnalysisSubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject_id', 'tag', 'surface', 'topography')
    ordering = ['id']
    search_fields = ("id", "tag__id", "surface__id", "topography__id")
    search_help_text = "Search by Subject ID or related Tag, Surface, or Topography ID"
    list_filter = [TagFilter, SurfaceFilter, TopographyFilter]

    @admin.display(description='Subject ID')
    def subject_id(self, obj):
        """Display the ID of whichever subject type is present (tag, surface, or topography) as a link."""
        subject = obj.get()
        if not subject:
            return None
        name = subject.__class__.__name__.lower()
        if name == "tag":
            return None
        url = reverse(f'admin:manager_{name}_change', args=[subject.id])
        return format_html('<a href="{}">{}</a>', url, subject.id)
