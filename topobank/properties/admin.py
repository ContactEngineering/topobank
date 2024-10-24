from django.contrib import admin

from topobank.properties.models import Property


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "value_categorical", "value_numerical", "unit")
