from django.contrib import admin

from .models import Surface, Topography


@admin.register(Surface)
class SurfaceAdmin(admin.ModelAdmin):
    pass


@admin.register(Topography)
class TopographyAdmin(admin.ModelAdmin):
    pass
