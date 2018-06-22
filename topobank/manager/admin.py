from django.contrib import admin

from .models import Topography

@admin.register(Topography)
class TopographyAdmin(admin.ModelAdmin):
    pass

