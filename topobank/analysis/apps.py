from django.apps import AppConfig


class AnalysisAppConfig(AppConfig):
    name = 'topobank.analysis'

    def ready(self):
        # Make sure the signals are registered now
        # Make sure Celery tasks are registered now
        import sds_workflows.features.feature_vector  # noqa: F401
        import sds_workflows.training.gpc  # noqa: F401

        # Import sds_workflows to trigger workflow registration
        import sds_workflows.training.gpr  # noqa: F401
        import sds_workflows.training.loo_folds  # noqa: F401
        import sds_workflows.training.prediction  # noqa: F401
        import sds_workflows.training.wlda  # noqa: F401

        from . import custodian  # noqa: F401
        from . import signals  # noqa: F401
        from . import tasks  # noqa: F401

        # Register muFlow bridge tasks
        from .muflow_bridge import tasks as muflow_tasks  # noqa: F401
