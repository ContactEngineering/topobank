from django.contrib import admin

from .models import Manifest, ManifestSet


@admin.register(Manifest)
class FileManifestAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "kind", "is_valid", "created_at", "updated_at")
    list_filter = ("kind",)
    ordering = ["-created_at"]


@admin.register(ManifestSet)
class ManifestSetAdmin(admin.ModelAdmin):
    list_display = ("id",)
