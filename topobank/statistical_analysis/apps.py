from django.apps import AppConfig


class StatisticalAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'topobank.statistical_analysis'

    def ready(self):
        # make sure the functions are registered now
        # noinspection PyUnresolvedReferences
        import topobank.statistical_analysis.functions
        # noinspection PyUnresolvedReferences
        import topobank.statistical_analysis.views
        # noinspection PyUnresolvedReferences
        import topobank.statistical_analysis.downloads


