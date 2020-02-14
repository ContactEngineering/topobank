from django.apps import AppConfig


class AnalysisAppConfig(AppConfig):
    name = 'topobank.analysis'

    def ready(self):
        # make sure the signals are registered now
        import topobank.analysis.signals
