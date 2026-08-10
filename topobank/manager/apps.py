from django.apps import AppConfig


class ManagerAppConfig(AppConfig):
    name = 'topobank.manager'

    def ready(self):
        # Make sure the signals are registered now
        # Make sure Celery tasks are registered now
        from . import custodian  # noqa: F401
        from . import signals  # noqa: F401
        from . import tasks  # noqa: F401

        # Register the built-in measurement types. `MeasurementsAppConfig` does
        # this too, and additionally discovers types provided by external
        # packages. Doing it here as well means the built-in kinds are always
        # available: `Measurement` is unusable without them, and a deployment that
        # has not (yet) added `topobank.measurements` to INSTALLED_APPS would
        # otherwise fail in a confusing way. Registration is idempotent.
        from ..measurements import types  # noqa: F401
