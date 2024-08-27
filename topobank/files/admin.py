from django.contrib import admin

from .models import Folder, Manifest


@admin.register(Manifest)
class FileManifestAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "folder", "kind", "is_valid", "created", "updated")
    list_filter = ("kind",)
    ordering = ["-created"]


@admin.register(Folder)
class FileParentAdmin(admin.ModelAdmin):
    list_display = ("id",)
