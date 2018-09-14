from django.contrib import admin

from .models import Analysis, AnalysisFunction


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    pass


@admin.register(AnalysisFunction)
class AnalysisFunctionAdmin(admin.ModelAdmin):
    pass
