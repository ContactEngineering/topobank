from django.apps import AppConfig


class AnalysisAppConfig(AppConfig):
    name = 'topobank.authorization'

    def ready(self):
        # make sure the signals are registered now
        # from . import signals  # noqa: F401
        pass
