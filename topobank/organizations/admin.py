from django import forms
from django.contrib import admin

from .models import Organization, get_plugin_choices


class OrganizationAdminForm(forms.ModelForm):
    """Custom form for Organization admin with better plugin selection widget."""

    plugins_available = forms.MultipleChoiceField(
        choices=get_plugin_choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select plugin packages available for this organization.",
    )

    class Meta:
        model = Organization
        fields = '__all__'

    def clean_plugins_available(self):
        """Convert form data to list for ArrayField."""
        return list(self.cleaned_data['plugins_available'])


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    form = OrganizationAdminForm
    list_display = ('id', 'name', 'group', 'plugins_available')
