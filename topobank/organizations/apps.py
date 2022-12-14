from django.apps import AppConfig


class OrganizationsAppConfig(AppConfig):
    """This app handles organizations.

    Organizations are needed to configure which plugins are available for
    a specific set of users."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'topobank.organizations'

    def ready(self):
        from . import signals



