from django.contrib import admin

from .models import Folder, Manifest


@admin.register(Manifest)
class FileManifestAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "folder", "kind", "is_valid", "created_at", "updated_at")
    list_filter = ("kind",)
    ordering = ["-created_at"]


@admin.register(Folder)
class FileParentAdmin(admin.ModelAdmin):
    list_display = ("id",)
