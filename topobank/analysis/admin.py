from django.contrib import admin

from .models import Analysis, AnalysisFunction


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_state', 'task_id', 'function', 'subject_type', 'subject_id', 'start_time')
    list_filter = ('task_state', 'function', 'subject_type')
    ordering = ['-start_time']


@admin.register(AnalysisFunction)
class AnalysisFunctionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['id']
