from django.contrib import admin

from .models import Surface, Topography


@admin.register(Surface)
class SurfaceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "creation_datetime")
    ordering = ["-creation_datetime"]


@admin.register(Topography)
class TopographyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "creation_datetime", "task_state", "task_id")
    list_filter = ("task_state",)
    ordering = ["-creation_datetime"]
