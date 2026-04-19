from django.apps import AppConfig


class AnalysisAppConfig(AppConfig):
    name = 'topobank.analysis'

    def ready(self):
        from . import custodian  # noqa: F401
        from . import signals  # noqa: F401
        from . import tasks  # noqa: F401

        # Register muFlow bridge tasks
        from .muflow_bridge import tasks as muflow_tasks  # noqa: F401
