from django.apps import AppConfig


class ContactAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'topobank.contact_analysis'

    def ready(self):
        # make sure the functions are registered now
        import topobank.contact_analysis.functions
