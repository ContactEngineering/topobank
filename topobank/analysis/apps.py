from django.apps import AppConfig


class AnalysisAppConfig(AppConfig):
    name = 'topobank.analysis'

    def ready(self):
        # Make sure the signals are registered now
        # Make sure Celery tasks are registered now
        from . import custodian  # noqa: F401
        from . import signals  # noqa: F401
        from . import tasks  # noqa: F401
