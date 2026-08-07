from django.apps import AppConfig


class MeasurementsAppConfig(AppConfig):
    """
    App that provides the measurement type registry.

    The app has no models of its own; it exists so that the built-in measurement
    types are registered, and third-party types discovered, once the app registry
    is ready.
    """

    name = "topobank.measurements"
    label = "measurements"

    def ready(self):
        # Importing the module registers the built-in types.
        from . import types  # noqa: F401
        from .registry import load_entry_points

        # Types shipped by external packages. Packages that are Django apps
        # themselves may alternatively register from their own `ready()`.
        load_entry_points()
