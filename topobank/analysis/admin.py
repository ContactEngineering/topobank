from django.contrib import admin

from .models import Analysis, AnalysisFunction, AnalysisSubject


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_state', 'task_id', 'function', 'subject_dispatch', 'start_time')
    list_filter = ('task_state', 'function')
    ordering = ['-start_time']


@admin.register(AnalysisFunction)
class AnalysisFunctionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['id']


@admin.register(AnalysisSubject)
class AnalysisSubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'collection', 'surface', 'topography')
    ordering = ['id']
