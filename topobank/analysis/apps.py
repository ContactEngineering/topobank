from django.apps import AppConfig


class AnalysisAppConfig(AppConfig):
    name = 'topobank.analysis'

    def ready(self):
        from . import custodian  # noqa: F401
        from . import signals  # noqa: F401
        from . import tasks  # noqa: F401

        # Register muFlow Celery tasks
        from .muflow import tasks as muflow_tasks  # noqa: F401
